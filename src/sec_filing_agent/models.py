"""Public, framework-independent models emitted by SEC collection services."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class FilingMetadata(BaseModel):
    """A filing selected from SEC submissions, with stable EDGAR provenance."""

    ticker: str
    cik: str
    title: str
    form_type: str
    filing_date: date | None = None
    report_date: date | None = None
    accession_number: str
    primary_document: str | None = None
    html_url: str
    archive_directory_url: str
    selection_reason: Literal["requested", "foreign_fallback"] = "requested"


class ParsedSection(BaseModel):
    """A bounded, citeable portion of a filing's main document."""

    filing_accession: str
    form_type: str
    report_date: date | None = None
    item_code: str
    label: str
    text: str
    source_url: str
    source_start: int | None = None
    source_end: int | None = None
    truncated: bool = False
    document_kind: Literal["primary", "archive_candidate", "complete_text"] = "primary"


class MetricValue(BaseModel):
    """One normalized XBRL fact together with the fields needed to audit it."""

    value: float
    unit: str
    end_date: date | None = None
    filed: date | None = None
    accession_number: str | None = None
    derived: bool = False
    namespace: str | None = None
    concept: str | None = None
    form: str | None = None
    fiscal_period: str | None = None
    frame: str | None = None
    start_date: date | None = None


class FiscalMetrics(BaseModel):
    ticker: str
    fiscal_year: int
    fiscal_period: str = "FY"
    facts: dict[str, MetricValue] = Field(default_factory=dict)


class CollectionResult(BaseModel):
    """The complete, best-effort result of a multi-ticker collection request."""

    filings: dict[str, list[FilingMetadata]] = Field(default_factory=dict)
    sections: dict[str, list[ParsedSection]] = Field(default_factory=dict)
    xbrl_metrics: dict[str, list[FiscalMetrics]] = Field(default_factory=dict)
    warnings: dict[str, list[str]] = Field(default_factory=dict)


class PlannerOutput(BaseModel):
    semantic_query: str = Field(
        description=(
            "English search text for retrieving relevant SEC filing passages. "
            "Preserve key concepts, negation, comparisons, and any constraints "
            "that cannot be represented by the structured filters."
        ),
    )
    tickers: tuple[str, ...] | None = Field(
        default=None,
        description=(
            "Uppercase stock ticker symbols explicitly requested by the user "
            "or unambiguously resolved from company names. Never guess. "
            "Null means no reliable ticker constraint."
        ),
    )
    form_types: tuple[str, ...] | None = Field(
        default=None,
        description=(
            "Explicitly requested SEC form types, such as 10-K, 10-Q, or 20-F. "
            "Do not infer 10-K solely from 'annual report'. "
            "Null means no form-type constraint."
        ),
    )
    report_date_from: date | None = Field(
        default=None,
        description=(
            "Inclusive lower bound on the reporting period end date, "
            "in YYYY-MM-DD format. Not the filing date or fiscal-year label. "
            "Null means no lower bound."
        ),
    )
    report_date_to: date | None = Field(
        default=None,
        description=(
            "Inclusive upper bound on the reporting period end date, "
            "in YYYY-MM-DD format. Not the filing date or fiscal-year label. "
            "Null means no upper bound."
        ),
    )
    item_codes: tuple[str, ...] | None = Field(
        default=None,
        description=(
            "Stored section item codes explicitly requested by the user. "
            "Do not infer section restrictions from search topics. "
            "Null means no section constraint."
        ),
    )


class RetrievalFilters(BaseModel):
    """Validated structured constraints for filing-chunk retrieval.

    None means the planner did not specify that constraint.
    """

    ciks: tuple[str, ...] | None = None
    form_types: tuple[str, ...] | None = None
    report_date_from: date | None = None
    report_date_to: date | None = None
    item_codes: tuple[str, ...] | None = None


class SearchResult(BaseModel):
    chunk_id: int
    score: float
    cik: str
    accession_number: str
    form_type: str
    report_date: date | None
    item_code: str
    content: str
    source_url: str
