"""Manual endpoints for materializing chunks from cleaned filing text."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from sec_filing_agent.db.session import SessionLocal
from sec_filing_agent.services.chunking_service import (
    ChunkingService,
    CleaningsNotFoundError,
)
from sec_filing_agent.services.cleaning_service import CorpusNotFoundError

router = APIRouter(prefix="/chunks", tags=["chunks"])


class ChunkingRequest(BaseModel):
    force: bool = False


class ChunkingResponse(BaseModel):
    ticker: str
    scanned_sections: int
    chunked_sections: int
    skipped_sections: int
    chunks_written: int


@router.post("/tickers/{ticker}", response_model=ChunkingResponse)
async def chunk_ticker(ticker: str, payload: ChunkingRequest) -> ChunkingResponse:
    async with SessionLocal() as session:
        try:
            summary = await ChunkingService(session).chunk_ticker(ticker, force=payload.force)
        except CorpusNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail="No persisted filing sections for ticker",
            ) from error
        except CleaningsNotFoundError as error:
            raise HTTPException(status_code=409, detail="Run cleanings before chunking") from error
    return ChunkingResponse(**summary.__dict__)
