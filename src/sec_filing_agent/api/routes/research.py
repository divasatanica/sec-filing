"""RAG retrieval endpoint."""

from fastapi import APIRouter

from sec_filing_agent.api.dependencies import ContainerDep
from sec_filing_agent.domain.research import ResearchQuery, ResearchResponse

router = APIRouter(prefix="/v1/research", tags=["research"])


@router.post(
    "/query",
    response_model=ResearchResponse,
    summary="Retrieve grounded SEC filing passages",
)
async def query_filings(request: ResearchQuery, container: ContainerDep) -> ResearchResponse:
    citations = await container.rag_engine.query(request)
    return ResearchResponse(answer=None, citations=list(citations))
