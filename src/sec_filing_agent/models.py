"""Public, framework-independent models emitted by SEC collection services."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class FilingMetadata(BaseModel):
    """A filing selected from SEC submissions, with stable EDGAR provenance."""

    ticker: str
    cik: str
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
