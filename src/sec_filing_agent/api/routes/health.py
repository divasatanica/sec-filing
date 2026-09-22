"""Operational endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel

from sec_filing_agent.core.config import get_settings
from sec_filing_agent.services.sec_client import get_current_cache_ticker_map

router = APIRouter(tags=["operations"])


class HealthResponse(BaseModel):
    status: str
    enviroment: str
    ticker_number: int


@router.get("/health", response_model=HealthResponse, summary="Check whether the API is running")
async def health() -> HealthResponse:
    settings = get_settings()
    ticker_map = get_current_cache_ticker_map()
    return HealthResponse(
        status="ok",
        enviroment=settings.environment,
        ticker_number=0 if ticker_map is None else len(ticker_map),
    )
