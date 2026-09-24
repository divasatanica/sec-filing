"""HTTP middleware shared by API routes."""

from __future__ import annotations

from time import perf_counter
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request
from starlette.responses import JSONResponse, Response

logger = structlog.get_logger(__name__)
REQUEST_ID_HEADER = "X-Request-ID"
MAX_REQUEST_ID_LENGTH = 128


def add_request_logging(app: FastAPI) -> None:
    """Add request context and one structured access-log event per request."""

    @app.middleware("http")
    async def log_request(request: Request, call_next) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER)
        if not request_id or len(request_id) > MAX_REQUEST_ID_LENGTH:
            request_id = str(uuid4())

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            http_method=request.method,
            http_path=request.url.path,
        )
        started_at = perf_counter()

        try:
            response = await call_next(request)
            duration_ms = round((perf_counter() - started_at) * 1_000, 2)
            response.headers[REQUEST_ID_HEADER] = request_id
            logger.info(
                "request_completed",
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            return response
        except Exception:
            # FastAPI handles expected HTTPException and validation responses itself.
            # This branch is the final guard for unexpected handler/service failures:
            # log the real exception, but never expose its implementation details over HTTP.
            duration_ms = round((perf_counter() - started_at) * 1_000, 2)
            logger.exception(
                "request_failed",
                status_code=500,
                duration_ms=duration_ms,
            )
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "request_id": request_id,
                },
                headers={REQUEST_ID_HEADER: request_id},
            )
        finally:
            structlog.contextvars.clear_contextvars()
