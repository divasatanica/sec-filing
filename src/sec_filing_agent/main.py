"""ASGI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from sec_filing_agent import __version__
from sec_filing_agent.api.router import api_router
from sec_filing_agent.core.config import Settings, get_settings
from sec_filing_agent.core.errors import CoreNotConfiguredError, FilingNotFoundError
from sec_filing_agent.services.container import build_container


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an app with explicit dependency composition for tests and deployment."""

    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved_settings.data_dir.mkdir(parents=True, exist_ok=True)
        app.state.container = build_container(resolved_settings)
        yield

    app = FastAPI(
        title=resolved_settings.app_name,
        version=__version__,
        description=(
            "A local HTTP boundary for SEC filing ingestion and retrieval-augmented research. "
            "Infrastructure adapters are intentionally supplied by the application owner."
        ),
        lifespan=lifespan,
    )

    @app.exception_handler(CoreNotConfiguredError)
    async def core_not_configured_handler(
        _: Request, error: CoreNotConfiguredError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=501,
            content={"detail": str(error), "code": "core_not_configured"},
        )

    @app.exception_handler(FilingNotFoundError)
    async def filing_not_found_handler(_: Request, error: FilingNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": str(error), "code": "filing_not_found"},
        )

    app.include_router(api_router)
    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run("sec_filing_agent.main:app", host=settings.host, port=settings.port, reload=False)
