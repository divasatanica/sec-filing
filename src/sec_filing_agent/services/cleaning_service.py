"""Deterministic, conservative cleaning of persisted SEC filing sections."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sec_filing_agent.db.tables import (
    CompanyTicker,
    Filing,
    FilingChunk,
    FilingSection,
    FilingSectionCleaning,
)

_ISOLATED_SYMBOLS = frozenset({"•", "o", "$", "%", "(", ")"})
_PAGE_NUMBER_PATTERN = re.compile(r"\d{1,4}")
_WHITESPACE_PATTERN = re.compile(r"\s+")


class CorpusNotFoundError(LookupError):
    """Raised when a ticker has no persisted raw sections to process."""


@dataclass(frozen=True)
class CleanedText:
    content: str
    content_hash: str
    is_indexable: bool
    exclusion_reason: str | None
    metadata: dict[str, Any]


@dataclass
class CleaningSummary:
    ticker: str
    scanned_sections: int = 0
    created_sections: int = 0
    updated_sections: int = 0
    skipped_sections: int = 0
    excluded_sections: int = 0
    invalidated_chunks: int = 0


@dataclass(frozen=True)
class ExclusionRule:
    """A declarative rule for sections that should not enter text retrieval."""

    reason: str
    content_matches: Callable[[str], bool]
    form_types: frozenset[str] | None = None
    item_codes: frozenset[str] | None = None

    def matches(self, *, content: str, form_type: str, item_code: str) -> bool:
        normalized_form_type = form_type.strip().upper()
        normalized_item_code = item_code.strip().upper()
        return (
            (self.form_types is None or normalized_form_type in self.form_types)
            and (self.item_codes is None or normalized_item_code in self.item_codes)
            and self.content_matches(content)
        )


def _is_financial_statements_cross_reference(content: str) -> bool:
    return (
        len(content) <= 1_000
        and "included commencing at page f-1" in content
        and "incorporated herein by reference" in content
    )


EXCLUSION_RULES: tuple[ExclusionRule, ...] = (
    ExclusionRule(
        reason="empty_after_cleaning",
        content_matches=lambda content: not content,
    ),
    ExclusionRule(
        reason="financial_statements_cross_reference",
        form_types=frozenset({"10-K", "10-K/A", "10-KT"}),
        item_codes=frozenset({"8"}),
        content_matches=_is_financial_statements_cross_reference,
    ),
)


def clean_section_text(*, content_raw: str, form_type: str, item_code: str) -> CleanedText:
    """Remove verified page furniture while preserving narrative and table content."""

    normalized_lines = [_normalize_line(line) for line in content_raw.splitlines()]
    remove_indices: set[int] = set()
    table_of_contents_removed = 0
    page_numbers_removed = 0

    for index, line in enumerate(normalized_lines):
        if line.casefold() != "table of contents":
            continue
        remove_indices.add(index)
        table_of_contents_removed += 1
        for neighbor in (index - 1, index + 1):
            is_adjacent_page_number = 0 <= neighbor < len(normalized_lines) and _is_page_number(
                normalized_lines[neighbor]
            )
            if is_adjacent_page_number:
                if neighbor not in remove_indices:
                    remove_indices.add(neighbor)
                    page_numbers_removed += 1

    isolated_symbols_removed = 0
    clean_lines: list[str] = []
    for index, line in enumerate(normalized_lines):
        if index in remove_indices or not line:
            continue
        if line in _ISOLATED_SYMBOLS:
            isolated_symbols_removed += 1
            continue
        clean_lines.append(line)

    content_clean = "\n".join(clean_lines)
    exclusion_reason = _exclusion_reason(content_clean, form_type=form_type, item_code=item_code)
    metadata: dict[str, Any] = {
        "input_char_count": len(content_raw),
        "output_char_count": len(content_clean),
        "table_of_contents_lines_removed": table_of_contents_removed,
        "adjacent_page_numbers_removed": page_numbers_removed,
        "isolated_symbol_lines_removed": isolated_symbols_removed,
    }
    if exclusion_reason:
        metadata["exclusion_reason"] = exclusion_reason

    return CleanedText(
        content=content_clean,
        content_hash=_content_hash(content_clean),
        is_indexable=exclusion_reason is None,
        exclusion_reason=exclusion_reason,
        metadata=metadata,
    )


class FilingCleaningService:
    """Persist the current cleaning output for all raw sections of one ticker."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def clean_ticker(self, ticker: str, *, force: bool = False) -> CleaningSummary:
        normalized_ticker = _normalize_ticker(ticker)
        summary = CleaningSummary(ticker=normalized_ticker)

        async with self._session.begin():
            rows = (
                await self._session.execute(
                    select(FilingSection, Filing.form_type)
                    .join(Filing, Filing.accession_number == FilingSection.accession_number)
                    .join(CompanyTicker, CompanyTicker.cik == Filing.cik)
                    .where(func.upper(CompanyTicker.ticker) == normalized_ticker)
                    .order_by(Filing.filing_date, FilingSection.id)
                )
            ).all()
            if not rows:
                raise CorpusNotFoundError(normalized_ticker)

            for section, form_type in rows:
                summary.scanned_sections += 1
                cleaning = await self._session.scalar(
                    select(FilingSectionCleaning).where(
                        FilingSectionCleaning.section_id == section.id
                    )
                )
                if (
                    cleaning is not None
                    and cleaning.source_content_hash == section.content_hash
                    and not force
                ):
                    summary.skipped_sections += 1
                    continue

                cleaned = clean_section_text(
                    content_raw=section.content_raw,
                    form_type=form_type,
                    item_code=section.item_code,
                )
                if cleaning is None:
                    self._session.add(
                        FilingSectionCleaning(
                            section_id=section.id,
                            content_clean=cleaned.content,
                            source_content_hash=section.content_hash,
                            content_hash=cleaned.content_hash,
                            is_indexable=cleaned.is_indexable,
                            exclusion_reason=cleaned.exclusion_reason,
                            cleaning_metadata=cleaned.metadata,
                        )
                    )
                    summary.created_sections += 1
                else:
                    deleted_chunks = await self._session.execute(
                        delete(FilingChunk).where(FilingChunk.cleaning_id == cleaning.id)
                    )
                    summary.invalidated_chunks += deleted_chunks.rowcount or 0
                    cleaning.content_clean = cleaned.content
                    cleaning.source_content_hash = section.content_hash
                    cleaning.content_hash = cleaned.content_hash
                    cleaning.is_indexable = cleaned.is_indexable
                    cleaning.exclusion_reason = cleaned.exclusion_reason
                    cleaning.cleaning_metadata = cleaned.metadata
                    summary.updated_sections += 1

                if not cleaned.is_indexable:
                    summary.excluded_sections += 1

        return summary


def _normalize_line(line: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", line).strip()


def _is_page_number(line: str) -> bool:
    return bool(_PAGE_NUMBER_PATTERN.fullmatch(line))


def _exclusion_reason(content: str, *, form_type: str, item_code: str) -> str | None:
    normalized = _WHITESPACE_PATTERN.sub(" ", content).casefold().strip()
    for rule in EXCLUSION_RULES:
        if rule.matches(content=normalized, form_type=form_type, item_code=item_code):
            return rule.reason
    return None


def _normalize_ticker(ticker: str) -> str:
    normalized = ticker.strip().upper()
    if not normalized:
        raise CorpusNotFoundError(ticker)
    return normalized


def _content_hash(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()
