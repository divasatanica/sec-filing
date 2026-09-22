"""Test Router"""

from fastapi import APIRouter
from pydantic import BaseModel

from sec_filing_agent.services.sec_client import get_ticker_map

router = APIRouter(tags=["test"])


class TestResponse(BaseModel):
    status: str
    data: object


@router.get(
    "/test/sec_ticker", response_model=TestResponse, summary="Check whether the API is running"
)
async def health() -> TestResponse:
    res = await get_ticker_map()
    return TestResponse(status="ok", data=res["AAPL"])
