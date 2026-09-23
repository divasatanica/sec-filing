import asyncio
from typing import Any

from sec_filing_agent.services.filing_collector import (
    FilingCollector,
    archive_urls_for,
    select_filings,
    submission_records,
)
from sec_filing_agent.services.sec_client import SecClientError


def submission_payload(*, include_history: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "filings": {
            "recent": {
                "accessionNumber": ["0000000001-25-000002"],
                "filingDate": ["2025-02-01"],
                "reportDate": ["2024-12-31"],
                "form": ["10-K"],
                "primaryDocument": ["annual.htm"],
            },
            "files": [],
        }
    }
    if include_history:
        payload["filings"]["files"] = [{"name": "CIK0000000001-submissions-001.json"}]
    return payload


class FakeSecClient:
    def __init__(self) -> None:
        self.historical_names: list[str] = []

    async def get_ticker_map(self) -> dict[str, dict[str, Any]]:
        return {"TEST": {"ticker": "TEST", "cik_str": 1}}

    async def get_submissions(self, cik10: str) -> dict[str, Any]:
        assert cik10 == "0000000001"
        return submission_payload(include_history=True)

    async def get_historical_submissions(self, filename: str) -> dict[str, Any]:
        self.historical_names.append(filename)
        return {
            "accessionNumber": ["0000000001-24-000001"],
            "filingDate": ["2024-02-01"],
            "reportDate": ["2023-12-31"],
            "form": ["10-K"],
            "primaryDocument": ["old.htm"],
        }

    async def get_text(self, url: str, *, accept: str = "") -> str:
        del accept
        if url.endswith("annual.htm"):
            return """
            Item 1. Business
            Current annual report business narrative that is long enough for downstream retrieval.
            Item 1A. Risk Factors
            Current annual report risk narrative that is long enough for downstream retrieval.
            Item 7. Management Discussion
            Current annual report management narrative that is long enough for downstream retrieval.
            Item 8. Financial Statements
            Current financial statement narrative has enough detail for retrieval.
            """
        raise SecClientError("not found", url=url, status_code=404)

    async def get_archive_index(self, archive_directory_url: str) -> dict[str, Any]:
        del archive_directory_url
        return {"directory": {"item": []}}

    async def get_company_facts(self, cik10: str) -> dict[str, Any]:
        assert cik10 == "0000000001"
        return {
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [
                                {
                                    "fy": "2024",
                                    "fp": "FY",
                                    "form": "10-K",
                                    "filed": "2025-02-01",
                                    "end": "2024-12-31",
                                    "accn": "0000000001-25-000002",
                                    "val": 123,
                                }
                            ]
                        }
                    }
                }
            }
        }


def test_collector_is_best_effort_and_optionally_merges_history() -> None:
    async def scenario() -> None:
        client = FakeSecClient()
        result = await FilingCollector(client).collect(
            [" test ", "MISSING"],
            ["10-k"],
            max_filings_per_ticker=2,
            include_historical=True,
        )

        assert client.historical_names == ["CIK0000000001-submissions-001.json"]
        assert [filing.accession_number for filing in result.filings["TEST"]] == [
            "0000000001-25-000002",
            "0000000001-24-000001",
        ]
        assert result.sections["TEST"]
        assert result.xbrl_metrics["TEST"][0].facts["revenue"].value == 123
        assert result.warnings["MISSING"] == ["ticker_not_found"]
        assert any(
            warning.startswith("primary_document_failed") for warning in result.warnings["TEST"]
        )

    asyncio.run(scenario())


def test_discovery_builds_archive_urls_and_uses_explicit_foreign_fallback() -> None:
    records = submission_records(
        {
            "accessionNumber": ["0000000001-25-000003"],
            "filingDate": ["2025-03-01"],
            "reportDate": ["2024-12-31"],
            "form": ["20-F"],
            "primaryDocument": ["foreign.htm"],
        }
    )
    filings, warnings = select_filings(
        records,
        ticker="FOREIGN",
        cik10="0000000001",
        requested_forms={"10-K"},
        limit=1,
    )

    assert warnings == ["foreign_fallback_used:20-F,20-F/A,40-F,40-F/A"]
    assert filings[0].selection_reason == "foreign_fallback"
    urls = archive_urls_for(filings[0])
    assert urls.directory.endswith("/1/000000000125000003")
    assert urls.primary_html and urls.primary_html.endswith("/foreign.htm")
    assert urls.complete_text.endswith("/1/0000000001-25-000003.txt")
