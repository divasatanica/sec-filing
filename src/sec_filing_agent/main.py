"""ASGI application entry point."""

import uvicorn
from fastapi import FastAPI

from sec_filing_agent import __version__
from sec_filing_agent.api.middleware import add_request_logging
from sec_filing_agent.api.router import api_router
from sec_filing_agent.core.config import Settings, get_settings
from sec_filing_agent.core.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the application with configuration injection for tests and deployment."""

    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings)

    app = FastAPI(
        title=resolved_settings.app_name,
        version=__version__,
        description="A minimal local HTTP service built with FastAPI.",
    )
    add_request_logging(app)
    app.include_router(api_router)
    return app


app = create_app()


def run() -> None:
    settings = get_settings("production")
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        reload=False,
        log_config=None,
        access_log=False,
    )
