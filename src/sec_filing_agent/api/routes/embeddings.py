"""Placeholder endpoints for embedding-index creation and retrieval."""

from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, Field

from sec_filing_agent.services.company_service import CompanyService
from sec_filing_agent.services.embedding.embedding_service import EmbeddingService

router = APIRouter(prefix="/embeddings", tags=["embeddings"])


class BuildIndexRequest(BaseModel):
    """Options controlling vector-index materialization for one ticker."""

    force: bool = False


class BuildIndexResponse(BaseModel):
    """Summary returned once index creation is implemented."""

    ticker: str
    status: str
    job_id: str


class SearchRequest(BaseModel):
    """A semantic-search query and its optional scope."""

    query: str = Field(min_length=1)
    ticker: str | None = None
    top_k: int = Field(default=5, ge=1, le=100)


class SearchResult(BaseModel):
    """One chunk selected by semantic search."""

    chunk_id: int
    score: float
    ticker: str
    accession_number: str
    item_code: str
    content: str
    source_url: str


class SearchResponse(BaseModel):
    """Results returned by a semantic search."""

    results: list[SearchResult]


async def build_index_job(job_id: UUID, cik: str, force: bool):
    await EmbeddingService().build_embedding_index(cik, force)


@router.post("/tickers/{ticker}/index", response_model=BuildIndexResponse)
async def build_index(
    ticker: str, payload: BuildIndexRequest, background_tasks: BackgroundTasks
) -> BuildIndexResponse:
    """Create or refresh the embedding index for one ticker's chunks."""
    cik = await CompanyService().get_cik_by_ticker(ticker)

    job_id = uuid4()
    background_tasks.add_task(build_index_job, job_id, cik, payload.force)

    return BuildIndexResponse(ticker=ticker, status="queued", job_id=str(job_id))


@router.post("/search", response_model=SearchResponse)
async def search(payload: SearchRequest) -> SearchResponse:
    """Search indexed filing chunks using a natural-language query."""
    return SearchResponse(results=[])
