from datetime import date

import pytest

from sec_filing_agent.models import FilingMetadata
from sec_filing_agent.services.filing_parser import extract_sections


def filing(form_type: str) -> FilingMetadata:
    return FilingMetadata(
        ticker="TEST",
        cik="0000000001",
        title="TEST CORP",
        form_type=form_type,
        filing_date=date(2025, 2, 1),
        report_date=date(2024, 12, 31),
        accession_number="0000000001-25-000001",
        html_url="https://www.sec.gov/example.html",
        archive_directory_url="https://www.sec.gov/archive",
    )


def test_parser_uses_body_heading_after_table_of_contents() -> None:
    content = """
    <html><body>
      <h1>TABLE OF CONTENTS</h1>
      <p>Item 1. Business</p><p>Item 1A. Risk Factors</p>
      <p>Item 7. Management Discussion</p><p>Item 8. Financial Statements</p>
      <h1>Item 1. Business</h1>
      <p>Body business narrative distinguishes itself from the table of contents.</p>
      <h1>Item 1A. Risk Factors</h1>
      <p>Body risk narrative with enough detail for downstream retrieval.</p>
      <h1>Item 7. Management Discussion</h1>
      <p>Body management discussion with operating context and material period changes.</p>
      <h1>Item 8. Financial Statements</h1><table><tr><td>Revenue</td><td>100</td></tr></table>
    </body></html>
    """

    parsed = extract_sections(
        content,
        filing("10-K"),
        source_url="https://www.sec.gov/example.html",
        document_kind="primary",
    )

    business = next(section for section in parsed.sections if section.item_code == "1")
    assert "Body business narrative" in business.text
    assert "TABLE OF CONTENTS" not in business.text
    assert any(warning.startswith("duplicate_heading_ignored:1:") for warning in parsed.warnings)
    financials = next(section for section in parsed.sections if section.item_code == "8")
    assert "Revenue 100" in financials.text


@pytest.mark.parametrize(
    ("form_type", "content", "item_code"),
    [
        (
            "10-Q",
            "PART I\n"
            "Item 1. Financial Statements\n"
            "Financial statement details that are long enough for a real section.\n"
            "Item 2. Management Discussion\n"
            "Management analysis details that are long enough for a real section.\n"
            "PART II\n"
            "Item 1A. Risk Factors\n"
            "Risk factor detail that is long enough for a real section.",
            "part_i_item_2",
        ),
        (
            "8-K",
            "Item 2.02 Results of Operations\nRelease details and financial results for investors.",
            "2.02",
        ),
        (
            "20-F",
            "Item 3. Key Information\nForeign issuer material information for investors.",
            "3",
        ),
        (
            "6-K",
            "Financial Results\nForeign issuer earnings release and results details.",
            "earnings_results",
        ),
        (
            "DEF 14A",
            "Proposal 1 Election of Directors\nProxy voting detail for shareholders.",
            "proposal_1",
        ),
    ],
)
def test_parser_supports_each_filing_family(form_type: str, content: str, item_code: str) -> None:
    parsed = extract_sections(
        content,
        filing(form_type),
        source_url="https://www.sec.gov/example.html",
        document_kind="complete_text",
    )
    assert item_code in {section.item_code for section in parsed.sections}


def test_parser_records_truncation_and_normalized_offsets() -> None:
    content = f"Item 2.02 Results\n{'x' * 300}"
    parsed = extract_sections(
        content,
        filing("8-K"),
        source_url="https://www.sec.gov/example.html",
        document_kind="primary",
        max_chars=100,
    )
    section = parsed.sections[0]
    assert section.truncated is True
    assert section.source_start == 0
    assert section.source_end and section.source_end > 100
    assert section.text.endswith("[... truncated for length ...]")


def test_parser_preserves_the_full_section_when_max_chars_is_none() -> None:
    content = f"Item 2.02 Results\n{'x' * 300}"

    parsed = extract_sections(
        content,
        filing("8-K"),
        source_url="https://www.sec.gov/example.html",
        document_kind="primary",
        max_chars=None,
    )

    section = parsed.sections[0]
    assert section.truncated is False
    assert len(section.text) > 300
    assert "[... truncated for length ...]" not in section.text
