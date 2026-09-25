import asyncio

from sqlalchemy import BigInteger

from sec_filing_agent.db.tables import FilingChunk, FilingSection, FilingSectionCleaning
from sec_filing_agent.services.cleaning_service import (
    FilingCleaningService,
    clean_section_text,
)


def test_cleaner_removes_verified_page_furniture_without_deduplicating_tables() -> None:
    raw = """Item 7. Management's Discussion
4
TABLE OF CONTENTS
•
Revenue 100
Revenue 100
$
5
Table of Contents
)
Operating income 20
"""

    cleaned = clean_section_text(content_raw=raw, form_type="10-K", item_code="7")

    assert raw.count("Revenue 100") == 2
    assert "TABLE OF CONTENTS" not in cleaned.content.upper()
    assert "\n4\n" not in f"\n{cleaned.content}\n"
    assert "\n5\n" not in f"\n{cleaned.content}\n"
    assert "\n•\n" not in f"\n{cleaned.content}\n"
    assert "\n$\n" not in f"\n{cleaned.content}\n"
    assert "\n)\n" not in f"\n{cleaned.content}\n"
    assert cleaned.content.count("Revenue 100") == 2
    assert cleaned.metadata["table_of_contents_lines_removed"] == 2
    assert cleaned.metadata["adjacent_page_numbers_removed"] == 2
    assert cleaned.metadata["isolated_symbol_lines_removed"] == 3
    assert cleaned.is_indexable is True


def test_cleaner_excludes_only_the_known_financial_statement_cross_reference() -> None:
    cross_reference = """Item 8. Financial Statements and Supplementary Data
The financial statements and supplementary data required by this item, including the report of our
independent registered public accounting firm and the notes thereto, are included commencing at
page F-1 of this Annual Report on Form 10-K and incorporated herein by reference.
"""
    no_material_changes = """Item 1A. Risk Factors
There have been no material changes from the risk factors previously disclosed in our Annual Report.
"""

    excluded = clean_section_text(content_raw=cross_reference, form_type="10-K/A", item_code="8")
    retained = clean_section_text(content_raw=no_material_changes, form_type="10-Q", item_code="1A")

    assert excluded.is_indexable is False
    assert excluded.exclusion_reason == "financial_statements_cross_reference"
    assert retained.is_indexable is True
    assert retained.exclusion_reason is None


class _Transaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        return None


class _Result:
    def __init__(
        self,
        rows: list[tuple[FilingSection, str]] | None = None,
        rowcount: int = 0,
    ) -> None:
        self._rows = rows or []
        self.rowcount = rowcount

    def all(self) -> list[tuple[FilingSection, str]]:
        return self._rows


class _CleaningSession:
    def __init__(self, section: FilingSection, cleaning: FilingSectionCleaning | None) -> None:
        self._section = section
        self._cleaning = cleaning
        self.added: list[object] = []
        self.deleted_chunks = 0

    def begin(self) -> _Transaction:
        return _Transaction()

    async def execute(self, statement: object) -> _Result:
        if getattr(statement, "is_delete", False):
            self.deleted_chunks += 2
            return _Result(rowcount=2)
        return _Result([(self._section, "10-K")])

    async def scalar(self, statement: object) -> FilingSectionCleaning | None:
        del statement
        return self._cleaning

    def add(self, value: object) -> None:
        self.added.append(value)


def _section(content_hash: str = "a" * 64) -> FilingSection:
    return FilingSection(
        id=7,
        accession_number="0000000001-25-000001",
        item_code="7",
        item_label="Item 7",
        content_raw="Item 7. Management Discussion\nBody text for cleaning.",
        source_url="https://www.sec.gov/example",
        document_kind="primary",
        content_hash=content_hash,
    )


def test_cleaning_service_is_idempotent_and_invalidates_chunks_when_forced() -> None:
    async def scenario() -> None:
        section = _section()
        existing = FilingSectionCleaning(
            id=11,
            section_id=section.id,
            content_clean="old clean text",
            source_content_hash=section.content_hash,
            content_hash="b" * 64,
            is_indexable=True,
            cleaning_metadata={},
        )
        session = _CleaningSession(section, existing)
        service = FilingCleaningService(session)  # type: ignore[arg-type]

        skipped = await service.clean_ticker("test")
        assert skipped.skipped_sections == 1
        assert session.deleted_chunks == 0

        refreshed = await service.clean_ticker("test", force=True)
        assert refreshed.updated_sections == 1
        assert refreshed.invalidated_chunks == 2
        assert session.deleted_chunks == 2
        assert existing.content_clean == "Item 7. Management Discussion\nBody text for cleaning."

    asyncio.run(scenario())


def test_cleaning_models_define_the_required_cascade_relationships() -> None:
    cleaning_fk = next(iter(FilingSectionCleaning.__table__.foreign_keys))
    chunk_fk = next(iter(FilingChunk.__table__.foreign_keys))

    assert cleaning_fk.ondelete == "CASCADE"
    assert chunk_fk.ondelete == "CASCADE"
    assert {column.name for column in FilingSectionCleaning.__table__.primary_key.columns} == {"id"}
    assert isinstance(FilingChunk.__table__.c.id.type, BigInteger)
