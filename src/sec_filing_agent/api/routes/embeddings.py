"""Placeholder endpoints for embedding-index creation and retrieval."""

from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from sec_filing_agent.services.company_service import CompanyService
from sec_filing_agent.services.embedding.embedding_service import EmbeddingService, RetrievalFilters
from sec_filing_agent.models import SearchResult, PlannerOutput
from sec_filing_agent.services.query_planner.planner import QueryPlanner


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


class SearchResponse(BaseModel):
    """Results returned by a semantic search."""

    plan: PlannerOutput
    results: list[SearchResult]


class PlannerRequest(BaseModel):
    """User query planner accepted"""

    query: str


class PlannerResponse(BaseModel):
    """Planned query returned by query planner"""

    query_plan: PlannerOutput


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

    planner = QueryPlanner()
    output = await planner.plan(payload.query)

    if output.tickers is None:
        raise HTTPException(400, 'No tickers extracted from "{payload.query}"')

    ciks = await CompanyService().get_cik_map(list(output.tickers))
    cik_list = tuple([ciks[ticker] for ticker in output.tickers])

    results = await EmbeddingService().search(
        output.semantic_query,
        payload.top_k,
        RetrievalFilters(
            ciks=cik_list,
            form_types=output.form_types,
            item_codes=output.item_codes,
            report_date_from=output.report_date_from,
            report_date_to=output.report_date_to,
        ),
    )

    return SearchResponse(results=results, plan=output)


@router.post("/planner/plan", response_model=PlannerResponse)
async def plan(payload: PlannerRequest) -> PlannerResponse:

    planner = QueryPlanner()
    output = await planner.plan(payload.query)

    return PlannerResponse(query_plan=output)
