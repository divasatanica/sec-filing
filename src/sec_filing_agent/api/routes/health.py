"""Operational endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel

from sec_filing_agent.api.dependencies import ContainerDep

router = APIRouter(tags=["operations"])


class HealthResponse(BaseModel):
    status: str
    environment: str


@router.get("/health", response_model=HealthResponse, summary="Check whether the API is running")
async def health(container: ContainerDep) -> HealthResponse:
    return HealthResponse(status="ok", environment=container.settings.environment)
