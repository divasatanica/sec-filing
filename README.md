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
uv run uvicorn sec_filing_agent.main:app --reload
```

## Configuration

Settings are read from `.env` or environment variables with the `APP_` prefix:

```dotenv
APP_HOST=127.0.0.1
APP_PORT=8000
```

## Add your API

Create a route module under `src/sec_filing_agent/api/routes/`, then include
its router in `src/sec_filing_agent/api/router.py`. Keep business logic outside
route functions as the project grows.

Run checks with:

```bash
uv run ruff check .
uv run pytest
```
