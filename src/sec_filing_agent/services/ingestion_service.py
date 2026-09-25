"""Persist collected SEC filing data with per-filing transaction boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from sec_filing_agent.db.tables import (
    Company,
    CompanyTicker,
    Filing,
    FilingSection,
    FinancialFact,
    IngestionRun,
)
from sec_filing_agent.models import FilingMetadata, FiscalMetrics, MetricValue, ParsedSection
from sec_filing_agent.services.filing_collector import FilingCollector


@dataclass(frozen=True)
class CollectedFinancialFact:
    """One normalized metric together with the fiscal container that selected it."""

    fiscal_year: int
    fiscal_period: str
    metric_key: str
    metric: MetricValue


class IngestionService:
    def __init__(
        self,
        session: AsyncSession,
        collector: FilingCollector,
    ) -> None:
        self._session = session
        self._collector = collector

    async def ingest_ticker(
        self,
        tickers: str | list[str],
        max_filings_per_ticker: int,
        form_type: str | list[str] = "10-K",
    ) -> None:
        """Collect tickers first, then persist each filing and its facts atomically."""

        ticker_list = _normalize_input(tickers, name="tickers")
        form_type_list = _normalize_input(form_type, name="form_type")
        runs = await self._start_runs(ticker_list)

        try:
            collection = await self._collector.collect(
                ticker_list,
                form_type_list,
                section_max_chars=None,
                max_filings_per_ticker=max_filings_per_ticker,
            )
        except Exception as error:
            await self._mark_runs_failed(runs, error)
            raise

        for ticker in ticker_list:
            await self._persist_ticker_collection(
                ticker=ticker,
                filings=collection.filings.get(ticker, []),
                sections=collection.sections.get(ticker, []),
                fiscal_metrics=collection.xbrl_metrics.get(ticker, []),
                collector_warnings=collection.warnings.get(ticker, []),
                run=runs[ticker],
            )

    async def _persist_ticker_collection(
        self,
        *,
        ticker: str,
        filings: list[FilingMetadata],
        sections: list[ParsedSection],
        fiscal_metrics: list[FiscalMetrics],
        collector_warnings: list[str],
        run: IngestionRun,
    ) -> None:
        warnings = list(collector_warnings)
        sections_by_accession = _group_sections_by_accession(sections)
        facts_by_accession, fact_warnings = _group_facts_by_accession(fiscal_metrics)
        warnings.extend(fact_warnings)

        filings_saved = 0
        sections_saved = 0
        facts_saved = 0
        for filing in filings:
            filing_facts = facts_by_accession.pop(filing.accession_number, [])
            filing_sections = sections_by_accession.get(filing.accession_number, [])
            try:
                await self.save_filing_bundle(
                    filing=filing,
                    sections=filing_sections,
                    facts=filing_facts,
                )
            except (ArithmeticError, SQLAlchemyError, ValueError) as error:
                warnings.append(
                    f"filing_persist_failed:{filing.accession_number}:{type(error).__name__}"
                )
                continue

            filings_saved += 1
            sections_saved += len(filing_sections)
            facts_saved += len(filing_facts)

        # Companyfacts selection should normally point to a requested filing. Do not
        # insert unmatched facts because their accession foreign key is absent here.
        for accession_number, facts in facts_by_accession.items():
            warnings.append(f"financial_facts_unselected_filing:{accession_number}:{len(facts)}")

        await self._finish_run(
            run,
            status="partial_failure" if warnings else "completed",
            filings_discovered=len(filings),
            filings_saved=filings_saved,
            sections_saved=sections_saved,
            facts_saved=facts_saved,
            warnings=warnings,
        )

    async def save_filing_bundle(
        self,
        *,
        filing: FilingMetadata,
        sections: list[ParsedSection],
        facts: list[CollectedFinancialFact],
    ) -> None:
        """Commit one filing, its parsed sections, and its matching XBRL facts together."""

        async with self._session.begin():
            await self._upsert_company(filing)
            await self._upsert_ticker(filing)
            await self._upsert_filing(filing)

            for section in sections:
                await self._upsert_section(section)
            for fact in facts:
                await self._upsert_financial_fact(filing, fact)

    async def _start_runs(self, tickers: list[str]) -> dict[str, IngestionRun]:
        """Record intent before SEC network I/O so interrupted runs remain visible."""

        runs = {ticker: IngestionRun(ticker=ticker, status="running") for ticker in tickers}
        self._session.add_all(runs.values())
        await self._session.commit()
        return runs

    async def _finish_run(
        self,
        run: IngestionRun,
        *,
        status: str,
        filings_discovered: int,
        filings_saved: int,
        sections_saved: int,
        facts_saved: int,
        warnings: list[str],
        error_message: str | None = None,
    ) -> None:
        """Persist the final audit state after all filings for one ticker are attempted."""

        run.status = status
        run.finished_at = datetime.now(UTC)
        run.filings_discovered = filings_discovered
        run.filings_saved = filings_saved
        run.sections_saved = sections_saved
        run.facts_saved = facts_saved
        run.warnings = warnings
        run.error_message = error_message
        await self._session.commit()

    async def _mark_runs_failed(
        self,
        runs: dict[str, IngestionRun],
        error: Exception,
    ) -> None:
        """Close audit records when collection fails before per-filing persistence begins."""

        finished_at = datetime.now(UTC)
        for run in runs.values():
            run.status = "failed"
            run.finished_at = finished_at
            run.error_message = f"collection_failed:{type(error).__name__}"
        await self._session.commit()

    async def _upsert_company(self, filing: FilingMetadata) -> None:
        company = await self._session.get(Company, filing.cik)

        if company is None:
            self._session.add(Company(cik=filing.cik, name=filing.title))
        elif filing.title:
            company.name = filing.title

    async def _upsert_ticker(self, filing: FilingMetadata) -> None:
        statement = select(CompanyTicker).where(
            CompanyTicker.ticker == filing.ticker,
            CompanyTicker.cik == filing.cik,
        )
        ticker_row = (await self._session.execute(statement)).scalar_one_or_none()

        if ticker_row is None:
            self._session.add(
                CompanyTicker(
                    cik=filing.cik,
                    ticker=filing.ticker,
                )
            )

    async def _upsert_filing(self, filing: FilingMetadata) -> None:
        row = await self._session.get(Filing, filing.accession_number)

        if row is None:
            self._session.add(
                Filing(
                    accession_number=filing.accession_number,
                    cik=filing.cik,
                    form_type=filing.form_type,
                    filing_date=filing.filing_date,
                    report_date=filing.report_date,
                    primary_document=filing.primary_document,
                    html_url=filing.html_url,
                    archive_directory_url=filing.archive_directory_url,
                    selection_reason=filing.selection_reason,
                    is_amendment=filing.form_type.endswith("/A"),
                )
            )
            return

        row.form_type = filing.form_type
        row.filing_date = filing.filing_date
        row.report_date = filing.report_date
        row.primary_document = filing.primary_document
        row.html_url = filing.html_url
        row.archive_directory_url = filing.archive_directory_url
        row.selection_reason = filing.selection_reason
        row.is_amendment = filing.form_type.endswith("/A")

    async def _upsert_section(self, section: ParsedSection) -> None:
        statement = select(FilingSection).where(
            FilingSection.accession_number == section.filing_accession,
            FilingSection.item_code == section.item_code,
            FilingSection.parser_version == "v1",
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()

        values = {
            "item_label": section.label,
            "content_raw": section.text,
            "source_url": section.source_url,
            "document_kind": section.document_kind,
            "source_start": section.source_start,
            "source_end": section.source_end,
            "truncated": section.truncated,
            "content_hash": sha256(section.text.encode("utf-8")).hexdigest(),
        }

        if row is None:
            self._session.add(
                FilingSection(
                    accession_number=section.filing_accession,
                    item_code=section.item_code,
                    parser_version="v1",
                    **values,
                )
            )
            return

        for field, value in values.items():
            setattr(row, field, value)

    async def _upsert_financial_fact(
        self,
        filing: FilingMetadata,
        collected_fact: CollectedFinancialFact,
    ) -> None:
        metric = collected_fact.metric
        accession_number = metric.accession_number
        if accession_number is None:
            raise ValueError("accession number could not be None")
        if accession_number != filing.accession_number:
            raise ValueError("financial fact accession does not match filing")

        fact_key = _financial_fact_key(accession_number, collected_fact.metric_key, metric)
        statement = select(FinancialFact).where(FinancialFact.fact_key == fact_key)
        row = (await self._session.execute(statement)).scalar_one_or_none()

        values = {
            "cik": filing.cik,
            "accession_number": accession_number,
            "metric_key": collected_fact.metric_key,
            "namespace": metric.namespace,
            "concept": metric.concept,
            "value_numeric": Decimal(str(metric.value)),
            "unit": metric.unit,
            "start_date": metric.start_date,
            "end_date": metric.end_date,
            "fiscal_year": collected_fact.fiscal_year,
            "fiscal_period": metric.fiscal_period or collected_fact.fiscal_period,
            "form_type": metric.form or filing.form_type,
            "filed_date": metric.filed,
            "frame": metric.frame,
            "is_instant": metric.start_date is None,
            "derived": metric.derived,
            "source_url": filing.html_url,
            "provenance": _fact_provenance(collected_fact),
        }

        if row is None:
            self._session.add(FinancialFact(fact_key=fact_key, **values))
            return

        for field, value in values.items():
            setattr(row, field, value)


def _normalize_input(value: str | list[str], *, name: str) -> list[str]:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise ValueError(f"{name} must be a string or a list of strings")

    normalized = list(dict.fromkeys(item.strip().upper() for item in values if item.strip()))
    if not normalized:
        raise ValueError(f"{name} must not be empty")
    return normalized


def _group_sections_by_accession(
    sections: list[ParsedSection],
) -> dict[str, list[ParsedSection]]:
    grouped: dict[str, list[ParsedSection]] = {}
    for section in sections:
        grouped.setdefault(section.filing_accession, []).append(section)
    return grouped


def _group_facts_by_accession(
    fiscal_metrics: list[FiscalMetrics],
) -> tuple[dict[str, list[CollectedFinancialFact]], list[str]]:
    grouped: dict[str, list[CollectedFinancialFact]] = {}
    warnings: list[str] = []
    for fiscal in fiscal_metrics:
        for metric_key, metric in fiscal.facts.items():
            accession_number = metric.accession_number
            if accession_number is None:
                warnings.append(
                    f"financial_fact_missing_accession:{metric_key}:FY{fiscal.fiscal_year}"
                )
                continue
            grouped.setdefault(accession_number, []).append(
                CollectedFinancialFact(
                    fiscal_year=fiscal.fiscal_year,
                    fiscal_period=fiscal.fiscal_period,
                    metric_key=metric_key,
                    metric=metric,
                )
            )
    return grouped, warnings


def _financial_fact_key(
    accession_number: str,
    metric_key: str,
    metric: MetricValue,
) -> str:
    """Build the non-null identity used for idempotent fact upserts."""

    parts = (
        accession_number,
        metric_key,
        metric.unit,
        _date_key(metric.start_date),
        _date_key(metric.end_date),
        metric.concept or "<none>",
    )
    return sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _fact_provenance(collected_fact: CollectedFinancialFact) -> dict[str, object]:
    """Keep the normalized XBRL selection fields as JSON-safe audit metadata."""

    metric = collected_fact.metric
    return {
        "source": "sec_companyfacts",
        "accession_number": metric.accession_number,
        "metric_key": collected_fact.metric_key,
        "namespace": metric.namespace,
        "concept": metric.concept,
        "unit": metric.unit,
        "fiscal_year": collected_fact.fiscal_year,
        "fiscal_period": metric.fiscal_period or collected_fact.fiscal_period,
        "form": metric.form,
        "filed_date": _date_key(metric.filed),
        "start_date": _date_key(metric.start_date),
        "end_date": _date_key(metric.end_date),
        "frame": metric.frame,
        "derived": metric.derived,
    }


def _date_key(value: date | None) -> str:
    return value.isoformat() if value is not None else "<none>"
