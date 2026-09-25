"""Top-level API router."""

from fastapi import APIRouter

from sec_filing_agent.api.routes import chunks, cleanings, embeddings, health, ingest, test

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(test.router)
api_router.include_router(ingest.router)
api_router.include_router(cleanings.router)
api_router.include_router(chunks.router)
api_router.include_router(embeddings.router)
