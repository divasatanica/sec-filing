"""Manual endpoints for materializing cleaned filing text."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from sec_filing_agent.db.session import SessionLocal
from sec_filing_agent.services.cleaning_service import CorpusNotFoundError, FilingCleaningService

router = APIRouter(prefix="/cleanings", tags=["cleanings"])


class CleaningRequest(BaseModel):
    force: bool = False


class CleaningResponse(BaseModel):
    ticker: str
    scanned_sections: int
    created_sections: int
    updated_sections: int
    skipped_sections: int
    excluded_sections: int
    invalidated_chunks: int


@router.post("/tickers/{ticker}", response_model=CleaningResponse)
async def clean_ticker(ticker: str, payload: CleaningRequest) -> CleaningResponse:
    async with SessionLocal() as session:
        try:
            summary = await FilingCleaningService(session).clean_ticker(ticker, force=payload.force)
        except CorpusNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail="No persisted filing sections for ticker",
            ) from error
    return CleaningResponse(**summary.__dict__)
