"""Token-bounded chunks derived from cleaned SEC filing sections."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256

import tiktoken
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sec_filing_agent.db.tables import (
    CompanyTicker,
    Filing,
    FilingChunk,
    FilingSection,
    FilingSectionCleaning,
)
from sec_filing_agent.services.cleaning_service import CorpusNotFoundError

ENCODING_NAME = "cl100k_base"
MAX_CHUNK_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 80
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_THOUSANDS_SEPARATED_NUMBER = re.compile(
    r"(?<![\d,])(?:[$€£]\s*)?\(?[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?\)?(?![\d,])"
)


class CleaningsNotFoundError(LookupError):
    """Raised when raw sections exist but have not been cleaned yet."""


@dataclass(frozen=True)
class ChunkText:
    content: str
    token_count: int


@dataclass
class ChunkingSummary:
    ticker: str
    scanned_sections: int = 0
    chunked_sections: int = 0
    skipped_sections: int = 0
    chunks_written: int = 0


class ChunkingService:
    """Persist chunks for the current cleanings of one ticker."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def chunk_ticker(self, ticker: str, *, force: bool = False) -> ChunkingSummary:
        normalized_ticker = ticker.strip().upper()
        if not normalized_ticker:
            raise CorpusNotFoundError(ticker)
        summary = ChunkingSummary(ticker=normalized_ticker)

        async with self._session.begin():
            raw_section_exists = await self._session.scalar(
                select(FilingSection.id)
                .join(Filing, Filing.accession_number == FilingSection.accession_number)
                .join(CompanyTicker, CompanyTicker.cik == Filing.cik)
                .where(func.upper(CompanyTicker.ticker) == normalized_ticker)
                .limit(1)
            )
            if raw_section_exists is None:
                raise CorpusNotFoundError(normalized_ticker)

            cleanings = (
                await self._session.scalars(
                    select(FilingSectionCleaning)
                    .join(FilingSection, FilingSection.id == FilingSectionCleaning.section_id)
                    .join(Filing, Filing.accession_number == FilingSection.accession_number)
                    .join(CompanyTicker, CompanyTicker.cik == Filing.cik)
                    .where(func.upper(CompanyTicker.ticker) == normalized_ticker)
                    .order_by(Filing.filing_date, FilingSection.id)
                )
            ).all()
            if not cleanings:
                raise CleaningsNotFoundError(normalized_ticker)

            for cleaning in cleanings:
                summary.scanned_sections += 1
                if not cleaning.is_indexable:
                    summary.skipped_sections += 1
                    continue

                existing_chunks = await self._session.scalar(
                    select(func.count())
                    .select_from(FilingChunk)
                    .where(FilingChunk.cleaning_id == cleaning.id)
                )
                if existing_chunks and not force:
                    summary.skipped_sections += 1
                    continue
                if existing_chunks:
                    await self._session.execute(
                        delete(FilingChunk).where(FilingChunk.cleaning_id == cleaning.id)
                    )

                chunks = build_chunks(cleaning.content_clean)
                self._session.add_all(
                    FilingChunk(
                        cleaning_id=cleaning.id,
                        chunk_index=index,
                        content=chunk.content,
                        token_count=chunk.token_count,
                        content_hash=_content_hash(chunk.content),
                    )
                    for index, chunk in enumerate(chunks)
                )
                summary.chunked_sections += 1
                summary.chunks_written += len(chunks)

        return summary


def build_chunks(
    content: str,
    *,
    max_tokens: int = MAX_CHUNK_TOKENS,
    overlap_tokens: int = CHUNK_OVERLAP_TOKENS,
) -> list[ChunkText]:
    """Chunk non-empty source lines without exceeding the configured token budget."""

    if max_tokens < 1:
        raise ValueError("max_tokens must be positive")
    if not 0 <= overlap_tokens < max_tokens:
        raise ValueError("overlap_tokens must be between zero and max_tokens - 1")

    encoding = _encoding()
    units = [
        unit
        for line in content.splitlines()
        if line.strip()
        for unit in _split_oversized_line(line.strip(), encoding, max_tokens, overlap_tokens)
    ]
    if not units:
        return []

    chunks: list[ChunkText] = []
    current: list[str] = []
    for unit in units:
        candidate = _join_units([*current, unit])
        if not current or _token_count(candidate, encoding) <= max_tokens:
            current.append(unit)
            continue

        current_content = _join_units(current)
        chunks.append(ChunkText(current_content, _token_count(current_content, encoding)))
        current = _overlap_with_next(
            current_content,
            unit,
            encoding=encoding,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        )

    if current:
        current_content = _join_units(current)
        chunks.append(ChunkText(current_content, _token_count(current_content, encoding)))
    return chunks


def _split_oversized_line(
    line: str,
    encoding: tiktoken.Encoding,
    max_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    if _token_count(line, encoding) <= max_tokens:
        return [line]

    sentences = [
        sentence.strip() for sentence in _SENTENCE_BOUNDARY.split(line) if sentence.strip()
    ]
    if len(sentences) > 1:
        units: list[str] = []
        for sentence in sentences:
            units.extend(_split_oversized_line(sentence, encoding, max_tokens, overlap_tokens))
        return units

    token_ids = encoding.encode(line)
    safe_boundaries = _safe_token_boundaries(line, token_ids, encoding)
    chunks: list[str] = []
    start = 0
    while start < len(token_ids):
        preferred_end = min(start + max_tokens, len(token_ids))
        end = preferred_end
        while end > start and end not in safe_boundaries:
            end -= 1
        if end == start:
            # A single protected atom larger than the configured chunk size is
            # exceptionally unlikely for SEC numeric values. Preserve it rather than
            # silently corrupting the value, even though this one chunk exceeds budget.
            end = next(
                boundary
                for boundary in range(preferred_end + 1, len(token_ids) + 1)
                if boundary in safe_boundaries
            )

        chunks.append(encoding.decode(token_ids[start:end]))
        if end == len(token_ids):
            break

        next_start = max(start + 1, end - overlap_tokens)
        while next_start > start and next_start not in safe_boundaries:
            next_start -= 1
        start = next_start if next_start > start else end
    return chunks


def _overlap_with_next(
    current_content: str,
    next_unit: str,
    *,
    encoding: tiktoken.Encoding,
    max_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    next_tokens = _token_count(next_unit, encoding)
    requested_overlap = min(overlap_tokens, max_tokens - next_tokens)
    for token_count in range(requested_overlap, -1, -1):
        overlap = _tail_by_tokens(current_content, token_count, encoding)
        candidate = _join_units([overlap, next_unit]) if overlap else next_unit
        if _token_count(candidate, encoding) <= max_tokens:
            return [overlap, next_unit] if overlap else [next_unit]
    return [next_unit]


def _tail_by_tokens(content: str, token_count: int, encoding: tiktoken.Encoding) -> str:
    if token_count == 0:
        return ""
    tokens = encoding.encode(content)
    safe_boundaries = _safe_token_boundaries(content, tokens, encoding)
    start = max(0, len(tokens) - token_count)
    while start > 0 and start not in safe_boundaries:
        start -= 1
    return encoding.decode(tokens[start:])


def _safe_token_boundaries(
    content: str,
    token_ids: list[int],
    encoding: tiktoken.Encoding,
) -> set[int]:
    """Return token boundaries that do not bisect a comma-separated numeric literal."""

    decoded, offsets = encoding.decode_with_offsets(token_ids)
    if decoded != content:
        raise ValueError("token decoding did not reproduce the source text")

    numeric_spans = [match.span() for match in _THOUSANDS_SEPARATED_NUMBER.finditer(content)]
    char_boundaries = [*offsets, len(content)]
    return {
        token_index
        for token_index, char_offset in enumerate(char_boundaries)
        if not any(start < char_offset < end for start, end in numeric_spans)
    }


def _join_units(units: list[str]) -> str:
    return "\n".join(unit for unit in units if unit)


def _token_count(content: str, encoding: tiktoken.Encoding) -> int:
    return len(encoding.encode(content))


@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding(ENCODING_NAME)


def _content_hash(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()
