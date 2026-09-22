"""Top-level API router."""

from fastapi import APIRouter

from sec_filing_agent.api.routes import health

api_router = APIRouter()
api_router.include_router(health.router)
