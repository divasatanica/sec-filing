import asyncio

import tiktoken

from sec_filing_agent.db.tables import FilingChunk, FilingSectionCleaning
from sec_filing_agent.services.chunking_service import ChunkingService, build_chunks


def _numeric_fragments(number: str) -> set[str]:
    return {
        number[start:end]
        for start in range(len(number))
        for end in range(start + 3, len(number) + 1)
    }


def test_chunks_respect_token_limit_and_preserve_overlap() -> None:
    content = "\n".join(
        [
            "alpha " * 12,
            "bravo " * 12,
            "charlie " * 12,
            "delta " * 12,
        ]
    )

    chunks = build_chunks(content, max_tokens=30, overlap_tokens=5)
    encoding = tiktoken.get_encoding("cl100k_base")

    assert len(chunks) > 1
    assert all(chunk.token_count <= 30 for chunk in chunks)
    overlap = encoding.decode(encoding.encode(chunks[0].content)[-5:])
    assert chunks[1].content.startswith(overlap)


def test_chunks_split_an_oversized_unpunctuated_line() -> None:
    content = "orbit " * 200

    chunks = build_chunks(content, max_tokens=25, overlap_tokens=5)

    assert len(chunks) > 1
    assert all(chunk.token_count <= 25 for chunk in chunks)
    assert all("orbit" in chunk.content for chunk in chunks)


def test_chunks_do_not_bisect_comma_separated_numbers() -> None:
    number = "$1,234,567.89"
    content = f"{'revenue ' * 8}{number} {'guidance ' * 12}"

    chunks = build_chunks(content, max_tokens=12, overlap_tokens=3)

    assert len(chunks) > 1
    assert any(number in chunk.content for chunk in chunks)
    numeric_fragments = _numeric_fragments(number)
    for chunk in chunks:
        contains_numeric_fragment = any(fragment in chunk.content for fragment in numeric_fragments)
        assert not contains_numeric_fragment or number in chunk.content


def test_chunks_preserve_a_numeric_atom_larger_than_the_configured_budget() -> None:
    number = "1,234,567,890"
    chunks = build_chunks(f"prefix {number} suffix", max_tokens=2, overlap_tokens=1)
    numeric_fragments = _numeric_fragments(number)

    def preserves_number(chunk_content: str) -> bool:
        return number in chunk_content or not any(
            fragment in chunk_content for fragment in numeric_fragments
        )

    assert any(number in chunk.content for chunk in chunks)
    assert all(preserves_number(chunk.content) for chunk in chunks)


def test_chunks_return_no_rows_for_empty_content() -> None:
    assert build_chunks("\n \n") == []


class _Transaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        return None


class _Rows:
    def __init__(self, rows: list[tuple[FilingSectionCleaning, str]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[FilingSectionCleaning, str]]:
        return self._rows


class _ChunkingSession:
    def __init__(self, cleaning: FilingSectionCleaning, cik: str) -> None:
        self._cleaning = cleaning
        self._cik = cik
        self._scalar_results = [1, 0]
        self.added: list[FilingChunk] = []

    def begin(self) -> _Transaction:
        return _Transaction()

    async def scalar(self, statement: object) -> int:
        del statement
        return self._scalar_results.pop(0)

    async def execute(self, statement: object) -> _Rows:
        del statement
        return _Rows([(self._cleaning, self._cik)])

    def add_all(self, values: object) -> None:
        self.added.extend(values)  # type: ignore[arg-type]


def test_chunking_persists_the_company_scope_on_new_chunks() -> None:
    async def scenario() -> None:
        cik = "0000123456"
        cleaning = FilingSectionCleaning(
            id=11,
            section_id=7,
            content_clean="Revenue grew meaningfully during the fiscal year.",
            source_content_hash="a" * 64,
            content_hash="b" * 64,
            is_indexable=True,
            cleaning_metadata={},
        )
        session = _ChunkingSession(cleaning, cik)
        service = ChunkingService(session)  # type: ignore[arg-type]

        summary = await service.chunk_ticker("TEST")

        assert summary.chunks_written == len(session.added)
        assert session.added
        assert {chunk.cik for chunk in session.added} == {cik}

    asyncio.run(scenario())
