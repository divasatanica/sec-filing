"""Operational endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["operations"])


class HealthResponse(BaseModel):
    status: str


@router.get("/health", response_model=HealthResponse, summary="Check whether the API is running")
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
