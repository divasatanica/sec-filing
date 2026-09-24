"""Test Router"""

from fastapi import APIRouter
from pydantic import BaseModel

from sec_filing_agent.services.filing_collector import FilingCollector
from sec_filing_agent.services.sec_client import SecClient, get_ticker_map

router = APIRouter(tags=["test"])


class TestResponse(BaseModel):
    status: str
    data: object


@router.get(
    "/test/sec_ticker_map", response_model=TestResponse, summary="Check whether the API is running"
)
async def health() -> TestResponse:
    res = await get_ticker_map()
    return TestResponse(status="ok", data=res["AAPL"])


@router.get(
    "/test/sec_ticker/{ticker}",
    response_model=TestResponse,
    summary="Get filing of specific ticker",
)
async def get_ticker(ticker: str) -> TestResponse:
    async with SecClient() as client:
        result = await FilingCollector(client).collect(
            tickers=[ticker],
            form_types=["10-K"],
            max_filings_per_ticker=1,
            include_historical=False,
        )
    return TestResponse(status="ok", data=result)
