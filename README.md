# FastAPI Service

A minimal FastAPI skeleton for a local HTTP service. It intentionally contains
no application-specific data models, infrastructure adapters, or business logic.

## Included

- Application factory in `src/sec_filing_agent/main.py`
- Central router in `src/sec_filing_agent/api/router.py`
- `GET /health` endpoint
- Typed environment configuration in `src/sec_filing_agent/core/config.py`
- `uv` dependency management and a small API test suite

## Quick start

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --dev
cp .env.example .env
uv run sec-filing-agent
```

The service listens on `http://127.0.0.1:8000` by default. Open
`http://127.0.0.1:8000/docs` for interactive API documentation.

For development with automatic reload:

```bash
uv run uvicorn sec_filing_agent.main:app --reload --no-access-log
```

## Configuration

Settings are read from `.env.{environment}` (for example, `.env.development`)
or environment variables with the `SEC_FILING_AGENT_` prefix:

```dotenv
SEC_FILING_AGENT_HOST=127.0.0.1
SEC_FILING_AGENT_PORT=8000
SEC_FILING_AGENT_LOG_LEVEL=INFO
# Defaults to false in development and true in other environments.
SEC_FILING_AGENT_LOG_JSON=true
```

## Logging

The service emits structured request logs through `structlog`. Every response
includes an `X-Request-ID`; callers may supply one to correlate work across
services. Development output is readable in a terminal. Production output is
one JSON object per line, including timestamp, level, logger, request ID,
method, path, response status, and duration.

Use `structlog.contextvars.bind_contextvars(user_id=...)` after authentication
to add safe application context to all logs produced during that request. Do
not write credentials, authorization headers, or sensitive request bodies to
logs.

## Add your API

Create a route module under `src/sec_filing_agent/api/routes/`, then include
its router in `src/sec_filing_agent/api/router.py`. Keep business logic outside
route functions as the project grows.

Run checks with:

```bash
uv run ruff check .
uv run pytest
```
