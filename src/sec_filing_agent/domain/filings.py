"""Models shared by the filing ingestion and lookup APIs."""

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl


class FilingForm(StrEnum):
    FORM_10_K = "10-K"
    FORM_10_Q = "10-Q"
    FORM_8_K = "8-K"
    FORM_6_K = "6-K"


class FilingReference(BaseModel):
    """The metadata required to find and retrieve an SEC filing."""

    instrument: str = Field(..., min_length=1, examples=["AAPL"])
    accession_number: str = Field(..., min_length=1, examples=["0000320193-25-000079"])
    form: FilingForm
    filed_at: date
    report_period: date | None = None
    primary_document: str | None = None
    source_url: HttpUrl | None = None
    items: list[str] = Field(default_factory=list, description="SEC item numbers, mainly for 8-Ks.")


class FilingListResponse(BaseModel):
    filings: list[FilingReference]
    next_cursor: str | None = None


class FilingSyncRequest(BaseModel):
    """A request to discover, download, parse and index relevant filings."""

    instruments: list[str] = Field(..., min_length=1, examples=[["AAPL", "MSFT"]])
    forms: list[FilingForm] = Field(
        default_factory=lambda: [FilingForm.FORM_10_K, FilingForm.FORM_10_Q, FilingForm.FORM_8_K]
    )
    from_date: date | None = None
    to_date: date | None = None
    force_reprocess: bool = False


class FilingSyncResponse(BaseModel):
    filings_processed: int
    completed_at: datetime
    status: str = "completed"
