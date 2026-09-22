"""Filing discovery, ingestion and lookup endpoints."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query

from sec_filing_agent.api.dependencies import ContainerDep
from sec_filing_agent.domain.filings import (
    FilingForm,
    FilingListResponse,
    FilingReference,
    FilingSyncRequest,
    FilingSyncResponse,
)

router = APIRouter(prefix="/v1", tags=["filings"])


@router.post(
    "/filings/sync",
    response_model=FilingSyncResponse,
    summary="Discover, persist and index filings",
)
async def sync_filings(request: FilingSyncRequest, container: ContainerDep) -> FilingSyncResponse:
    """Run the ingestion flow; swap this for a job queue if ingestion becomes long-running."""

    filings_processed = await container.ingestion.sync(request)
    return FilingSyncResponse(
        filings_processed=filings_processed,
        completed_at=datetime.now(UTC),
    )


@router.get(
    "/instruments/{instrument}/filings",
    response_model=FilingListResponse,
    summary="List filings known to the local repository",
)
async def list_filings(
    instrument: str,
    container: ContainerDep,
    forms: Annotated[list[FilingForm] | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> FilingListResponse:
    filings, next_cursor = await container.repository.list_filings(
        instrument=instrument.upper(), forms=forms or [], cursor=cursor, limit=limit
    )
    return FilingListResponse(filings=list(filings), next_cursor=next_cursor)


@router.get(
    "/filings/{accession_number}",
    response_model=FilingReference,
    summary="Get filing metadata by SEC accession number",
)
async def get_filing(accession_number: str, container: ContainerDep) -> FilingReference:
    return await container.repository.get_filing(accession_number=accession_number)
