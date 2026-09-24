from fastapi import APIRouter
from pydantic import BaseModel, Field

from sec_filing_agent.db.session import SessionLocal
from sec_filing_agent.services.filing_collector import FilingCollector
from sec_filing_agent.services.ingestion_service import IngestionService
from sec_filing_agent.services.sec_client import SecClient

router = APIRouter(prefix="/ingestions", tags=["ingestions"])


class IngestionRequest(BaseModel):
    form_types: list[str] = Field(default_factory=lambda: ["10-K"], min_length=1)
    max_filings_per_ticker: int = Field(default=3, ge=1, le=50)


@router.post("/tickers/{ticker}")
async def ingest_ticker(
    ticker: str,
    payload: IngestionRequest,
) -> dict[str, str]:
    async with SecClient() as client:
        collector = FilingCollector(client)

        async with SessionLocal() as session:
            service = IngestionService(
                session=session,
                collector=collector,
            )

            await service.ingest_ticker(
                ticker,
                form_type=payload.form_types,
                max_filings_per_ticker=payload.max_filings_per_ticker,
            )

    return {
        "status": "completed",
        "ticker": ticker.upper(),
    }
