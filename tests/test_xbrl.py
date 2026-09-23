from datetime import date

from sec_filing_agent.models import FilingMetadata
from sec_filing_agent.services.xbrl import extract_annual_metrics


def selected_filing() -> FilingMetadata:
    return FilingMetadata(
        ticker="TEST",
        cik="0000000001",
        form_type="10-K/A",
        filing_date=date(2025, 2, 1),
        report_date=date(2024, 12, 31),
        accession_number="0000000001-25-000001",
        html_url="https://www.sec.gov/example.html",
        archive_directory_url="https://www.sec.gov/archive",
    )


def annual_fact(value: float, **overrides: str | float) -> dict[str, str | float]:
    return {
        "fy": "2024",
        "fp": "FY",
        "form": "10-K/A",
        "filed": "2025-02-01",
        "end": "2024-12-31",
        "start": "2024-01-01",
        "accn": "0000000001-25-000001",
        "frame": "CY2024",
        "val": value,
        **overrides,
    }


def test_us_gaap_prefers_selected_amendment_and_derives_fcf() -> None:
    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            annual_fact(100),
                            annual_fact(
                                200,
                                accn="0000000001-26-000001",
                                filed="2026-02-01",
                            ),
                        ]
                    }
                },
                "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [annual_fact(50)]}},
                "PaymentsToAcquirePropertyPlantAndEquipment": {
                    "units": {"USD": [annual_fact(-10)]}
                },
            }
        }
    }

    result = extract_annual_metrics(facts, ticker="TEST", selected_filings=[selected_filing()])

    assert result.warnings == []
    metrics = result.fiscal_metrics[0]
    assert metrics.facts["revenue"].value == 100
    assert metrics.facts["revenue"].accession_number == "0000000001-25-000001"
    assert metrics.facts["freeCashFlow"].value == 40
    assert metrics.facts["freeCashFlow"].derived is True
    assert metrics.facts["revenue"].start_date == date(2024, 1, 1)


def test_ifrs_and_custom_namespaces_are_supported() -> None:
    ifrs = {"facts": {"ifrs-full": {"Revenue": {"units": {"EUR": [annual_fact(90, form="20-F")]}}}}}
    custom = {"facts": {"issuer-custom": {"Revenues": {"units": {"USD": [annual_fact(80)]}}}}}

    ifrs_result = extract_annual_metrics(ifrs, ticker="TEST", selected_filings=[])
    custom_result = extract_annual_metrics(custom, ticker="TEST", selected_filings=[])

    assert ifrs_result.fiscal_metrics[0].facts["revenue"].unit == "EUR"
    assert custom_result.fiscal_metrics[0].facts["revenue"].namespace == "issuer-custom"


def test_fcf_is_not_derived_from_incompatible_units_and_empty_facts_warn() -> None:
    facts = {
        "facts": {
            "us-gaap": {
                "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [annual_fact(50)]}},
                "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"EUR": [annual_fact(10)]}},
            }
        }
    }
    result = extract_annual_metrics(facts, ticker="TEST", selected_filings=[])

    assert "freeCashFlow" not in result.fiscal_metrics[0].facts
    assert extract_annual_metrics({}, ticker="TEST", selected_filings=[]).warnings == [
        "companyfacts_missing_facts"
    ]
