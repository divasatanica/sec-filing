"""Models for RAG retrieval and answer-generation endpoints."""

from datetime import date

from pydantic import BaseModel, Field

from sec_filing_agent.domain.filings import FilingForm


class ResearchFilters(BaseModel):
    instruments: list[str] = Field(default_factory=list)
    forms: list[FilingForm] = Field(default_factory=list)
    from_date: date | None = None
    to_date: date | None = None
    accession_numbers: list[str] = Field(default_factory=list)


class ResearchQuery(BaseModel):
    query: str = Field(..., min_length=1, examples=["What did management say about iPhone demand?"])
    filters: ResearchFilters = Field(default_factory=ResearchFilters)
    top_k: int = Field(default=8, ge=1, le=50)


class Citation(BaseModel):
    instrument: str
    accession_number: str
    form: FilingForm
    chunk_id: str
    text: str
    score: float


class ResearchResponse(BaseModel):
    answer: str | None = Field(
        default=None,
        description="Optional generated answer. Retrieval-only implementations may return null.",
    )
    citations: list[Citation]
