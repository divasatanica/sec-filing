"""Framework-independent orchestration of SEC discovery, parsing, and XBRL extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from sec_filing_agent.models import CollectionResult, FilingMetadata
from sec_filing_agent.services.filing_parser import MAX_SECTION_CHARS, extract_sections
from sec_filing_agent.services.sec_client import (
    SEC_BASE_DOMAIN,
    SecClient,
    SecClientError,
    cik_to_10digits,
    cik_to_archive_path,
)
from sec_filing_agent.services.xbrl import extract_annual_metrics

DocumentKind = Literal["primary", "archive_candidate", "complete_text"]

ANNUAL_DOMESTIC_FORMS = {"10-K", "10-K/A", "10-KT"}
QUARTERLY_DOMESTIC_FORMS = {"10-Q", "10-Q/A"}
EVENT_DOMESTIC_FORMS = {"8-K", "8-K/A"}
FOREIGN_FALLBACKS = {
    "annual": ("20-F", "20-F/A", "40-F", "40-F/A"),
    "quarterly": ("6-K", "6-K/A"),
    "event": ("6-K", "6-K/A"),
}


@dataclass(frozen=True)
class ArchiveUrls:
    directory: str
    primary_html: str | None
    filing_index: str
    complete_text: str


@dataclass(frozen=True)
class FetchedDocument:
    content: str
    source_url: str
    document_kind: DocumentKind


@dataclass
class FetchDocumentResult:
    document: FetchedDocument | None
    warnings: list[str]


class FilingCollector:
    """Collect SEC source documents and normalized financial facts for one or more tickers."""

    def __init__(self, client: SecClient) -> None:
        self._client = client

    async def collect(
        self,
        tickers: list[str],
        form_types: list[str] | tuple[str, ...] = ("10-K",),
        max_filings_per_ticker: int = 50,
        *,
        include_historical: bool = False,
        section_max_chars: int | None = MAX_SECTION_CHARS,
    ) -> CollectionResult:
        if not 1 <= max_filings_per_ticker <= 50:
            raise ValueError("max_filings_per_ticker must be between 1 and 50")
        if section_max_chars is not None and section_max_chars < 1:
            raise ValueError("section_max_chars must be positive or None")
        normalized_tickers = _normalize_tickers(tickers)
        normalized_forms = _normalize_forms(form_types)
        if not normalized_tickers:
            raise ValueError("at least one ticker is required")
        if not normalized_forms:
            raise ValueError("at least one form type is required")

        result = CollectionResult()
        ticker_map = await self._client.get_ticker_map()
        # Keep ticker processing sequential here. SecClient centralizes pacing, and this
        # makes a partial response deterministic; callers can add bounded concurrency later.
        for ticker in normalized_tickers:
            await self._collect_ticker(
                result,
                ticker=ticker,
                ticker_map=ticker_map,
                requested_forms=normalized_forms,
                max_filings_per_ticker=max_filings_per_ticker,
                include_historical=include_historical,
                section_max_chars=section_max_chars,
            )
        return result

    async def _collect_ticker(
        self,
        result: CollectionResult,
        *,
        ticker: str,
        ticker_map: dict[str, dict[str, Any]],
        requested_forms: set[str],
        max_filings_per_ticker: int,
        include_historical: bool,
        section_max_chars: int | None,
    ) -> None:
        # Materialize every output bucket even on failure so API/RAG callers do not have
        # to distinguish an unknown ticker from an omitted response key.
        result.filings[ticker] = []
        result.sections[ticker] = []
        result.xbrl_metrics[ticker] = []
        result.warnings[ticker] = []
        company = ticker_map.get(ticker)
        if not company:
            result.warnings[ticker].append("ticker_not_found")
            return
        try:
            cik10 = cik_to_10digits(company["cik_str"])
        except (KeyError, TypeError, ValueError):
            result.warnings[ticker].append("ticker_has_invalid_cik")
            return

        try:
            records, submission_warnings = await self._submission_records(
                cik10, include_historical=include_historical
            )
        except SecClientError as error:
            result.warnings[ticker].append(_request_warning("submissions_failed", error))
            return

        filings, selection_warnings = select_filings(
            records,
            ticker=ticker,
            cik10=cik10,
            requested_forms=requested_forms,
            limit=max_filings_per_ticker,
        )
        result.filings[ticker] = filings
        result.warnings[ticker].extend(submission_warnings)
        result.warnings[ticker].extend(selection_warnings)

        for filing in filings:
            fetched = await self._fetch_primary_document(filing)
            result.warnings[ticker].extend(fetched.warnings)
            if fetched.document is None:
                continue
            parsed = extract_sections(
                fetched.document.content,
                filing,
                source_url=fetched.document.source_url,
                document_kind=fetched.document.document_kind,
                max_chars=section_max_chars,
            )
            result.sections[ticker].extend(parsed.sections)
            result.warnings[ticker].extend(
                f"{warning}:{filing.accession_number}" for warning in parsed.warnings
            )

        try:
            company_facts = await self._client.get_company_facts(cik10)
        except SecClientError as error:
            result.warnings[ticker].append(_request_warning("companyfacts_failed", error))
            return
        xbrl = extract_annual_metrics(
            company_facts,
            ticker=ticker,
            selected_filings=filings,
        )
        result.xbrl_metrics[ticker] = xbrl.fiscal_metrics
        result.warnings[ticker].extend(xbrl.warnings)

    async def _submission_records(
        self, cik10: str, *, include_historical: bool
    ) -> tuple[list[dict[str, Any]], list[str]]:
        submission = await self._client.get_submissions(cik10)
        payloads = [submission]
        warnings: list[str] = []
        if include_historical:
            # SEC stores older submissions in separate files. A failure in one history
            # shard is observable, but should not discard recent filings or other shards.
            files = submission.get("filings", {}).get("files", [])
            if isinstance(files, list):
                for file_entry in files:
                    filename = file_entry.get("name") if isinstance(file_entry, dict) else None
                    if not isinstance(filename, str):
                        continue
                    try:
                        payloads.append(await self._client.get_historical_submissions(filename))
                    except (SecClientError, ValueError) as error:
                        warnings.append(
                            f"historical_submissions_failed:{filename}:{type(error).__name__}"
                        )

        records = []
        for payload in payloads:
            records.extend(submission_records(payload))
        deduplicated = {record["accession_number"]: record for record in records}
        return list(deduplicated.values()), warnings

    async def _fetch_primary_document(self, filing: FilingMetadata) -> FetchDocumentResult:
        urls = archive_urls_for(filing)
        warnings: list[str] = []
        if urls.primary_html:
            try:
                return FetchDocumentResult(
                    FetchedDocument(
                        content=await self._client.get_text(urls.primary_html),
                        source_url=urls.primary_html,
                        document_kind="primary",
                    ),
                    warnings,
                )
            except SecClientError as error:
                warnings.append(
                    _request_warning("primary_document_failed", error, filing.accession_number)
                )

        try:
            # primaryDocument is occasionally empty or unavailable; index.json is the
            # machine-readable fallback before falling back to the full submission text.
            archive_index = await self._client.get_archive_index(urls.directory)
            for candidate in _archive_html_candidates(archive_index):
                candidate_url = f"{urls.directory}/{candidate}"
                try:
                    return FetchDocumentResult(
                        FetchedDocument(
                            content=await self._client.get_text(candidate_url),
                            source_url=candidate_url,
                            document_kind="archive_candidate",
                        ),
                        warnings,
                    )
                except SecClientError as error:
                    warnings.append(_request_warning("archive_candidate_failed", error, candidate))
        except SecClientError as error:
            warnings.append(
                _request_warning("archive_index_failed", error, filing.accession_number)
            )

        try:
            return FetchDocumentResult(
                FetchedDocument(
                    content=await self._client.get_text(urls.complete_text, accept="text/plain"),
                    source_url=urls.complete_text,
                    document_kind="complete_text",
                ),
                warnings,
            )
        except SecClientError as error:
            warnings.append(
                _request_warning("complete_text_failed", error, filing.accession_number)
            )
            return FetchDocumentResult(None, warnings)


async def collect_sec_filings(
    client: SecClient,
    tickers: list[str],
    form_types: list[str] | tuple[str, ...] = ("10-K",),
    max_filings_per_ticker: int = 50,
    *,
    include_historical: bool = False,
) -> CollectionResult:
    """Convenience wrapper for callers that do not need to retain a collector instance."""

    return await FilingCollector(client).collect(
        tickers,
        form_types,
        max_filings_per_ticker,
        include_historical=include_historical,
    )


def submission_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Zip SEC's parallel submission arrays into validated filing records."""

    filings = payload.get("filings")
    arrays = filings.get("recent") if isinstance(filings, dict) else payload
    if not isinstance(arrays, dict):
        return []
    accession_numbers = arrays.get("accessionNumber")
    if not isinstance(accession_numbers, list):
        return []
    records = []
    for index, accession_number in enumerate(accession_numbers):
        if not isinstance(accession_number, str) or not accession_number:
            continue
        form = _parallel_value(arrays, "form", index)
        if not isinstance(form, str):
            continue
        records.append(
            {
                "accession_number": accession_number,
                "form": form.upper(),
                "filing_date": _parallel_value(arrays, "filingDate", index),
                "report_date": _parallel_value(arrays, "reportDate", index),
                "primary_document": _parallel_value(arrays, "primaryDocument", index),
            }
        )
    return records


def select_filings(
    records: list[dict[str, Any]],
    *,
    ticker: str,
    cik10: str,
    requested_forms: set[str],
    limit: int,
) -> tuple[list[FilingMetadata], list[str]]:
    """Select exact requested forms, falling back only for foreign issuer equivalents."""

    # Do not silently substitute a foreign form when an explicitly requested US form exists.
    exact = [record for record in records if record["form"] in requested_forms]
    selection_reason: Literal["requested", "foreign_fallback"] = "requested"
    warnings: list[str] = []
    if not exact:
        fallback_forms = _foreign_fallback_forms(requested_forms)
        if fallback_forms:
            exact = [record for record in records if record["form"] in fallback_forms]
            if exact:
                selection_reason = "foreign_fallback"
                warnings.append(f"foreign_fallback_used:{','.join(sorted(fallback_forms))}")
    if not exact:
        return [], ["requested_form_not_found"]

    unique_records = {record["accession_number"]: record for record in exact}
    ordered = sorted(
        unique_records.values(),
        key=lambda record: str(record.get("filing_date") or ""),
        reverse=True,
    )[:limit]
    return [
        filing_metadata_from_record(
            record,
            ticker=ticker,
            cik10=cik10,
            selection_reason=selection_reason,
        )
        for record in ordered
    ], warnings


def filing_metadata_from_record(
    record: dict[str, Any],
    *,
    ticker: str,
    cik10: str,
    selection_reason: Literal["requested", "foreign_fallback"],
) -> FilingMetadata:
    accession_number = str(record["accession_number"])
    primary_document = record.get("primary_document")
    primary_document = (
        primary_document if isinstance(primary_document, str) and primary_document else None
    )
    archive_directory = (
        f"{SEC_BASE_DOMAIN}/Archives/edgar/data/{cik_to_archive_path(cik10)}/"
        f"{accession_number.replace('-', '')}"
    )
    html_url = (
        f"{archive_directory}/{primary_document}"
        if primary_document
        else f"{archive_directory}/{accession_number}-index.html"
    )
    return FilingMetadata(
        ticker=ticker,
        cik=cik10,
        form_type=str(record["form"]),
        filing_date=_date_or_none(record.get("filing_date")),
        report_date=_date_or_none(record.get("report_date")),
        accession_number=accession_number,
        primary_document=primary_document,
        html_url=html_url,
        archive_directory_url=archive_directory,
        selection_reason=selection_reason,
    )


def archive_urls_for(filing: FilingMetadata) -> ArchiveUrls:
    primary_html = (
        f"{filing.archive_directory_url}/{filing.primary_document}"
        if filing.primary_document
        else None
    )
    return ArchiveUrls(
        directory=filing.archive_directory_url,
        primary_html=primary_html,
        filing_index=f"{filing.archive_directory_url}/{filing.accession_number}-index.html",
        complete_text=(
            f"{SEC_BASE_DOMAIN}/Archives/edgar/data/{cik_to_archive_path(filing.cik)}/"
            f"{filing.accession_number}.txt"
        ),
    )


def _archive_html_candidates(index: dict[str, Any]) -> list[str]:
    items = index.get("directory", {}).get("item", [])
    if not isinstance(items, list):
        return []
    candidates = []
    for item in items:
        name = item.get("name") if isinstance(item, dict) else None
        if not isinstance(name, str):
            continue
        normalized = name.lower()
        if not re.search(r"\.html?$", normalized):
            continue
        if "index" in normalized or normalized.startswith("ex-") or "exhibit" in normalized:
            continue
        candidates.append(name)
    return candidates


def _foreign_fallback_forms(requested_forms: set[str]) -> set[str]:
    fallback = set()
    if requested_forms & ANNUAL_DOMESTIC_FORMS:
        fallback.update(FOREIGN_FALLBACKS["annual"])
    if requested_forms & QUARTERLY_DOMESTIC_FORMS:
        fallback.update(FOREIGN_FALLBACKS["quarterly"])
    if requested_forms & EVENT_DOMESTIC_FORMS:
        fallback.update(FOREIGN_FALLBACKS["event"])
    return fallback


def _parallel_value(arrays: dict[str, Any], key: str, index: int) -> Any:
    values = arrays.get(key)
    return values[index] if isinstance(values, list) and index < len(values) else None


def _date_or_none(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _normalize_tickers(tickers: list[str]) -> list[str]:
    return list(dict.fromkeys(ticker.strip().upper() for ticker in tickers if ticker.strip()))


def _normalize_forms(form_types: list[str] | tuple[str, ...]) -> set[str]:
    return {form.strip().upper() for form in form_types if form.strip()}


def _request_warning(prefix: str, error: SecClientError, detail: str | None = None) -> str:
    suffix = detail or error.url
    status = error.status_code if error.status_code is not None else type(error).__name__
    return f"{prefix}:{suffix}:{status}"
