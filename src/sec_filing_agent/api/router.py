"""Top-level API router."""

from fastapi import APIRouter

from sec_filing_agent.api.routes import filings, health, research

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(filings.router)
api_router.include_router(research.router)
