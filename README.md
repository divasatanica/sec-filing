# SEC Filing Agent

A FastAPI skeleton plus a framework-independent SEC EDGAR collection layer.

## Included

- Application factory in `src/sec_filing_agent/main.py`
- Central router in `src/sec_filing_agent/api/router.py`
- `GET /health` endpoint
- Typed environment configuration in `src/sec_filing_agent/core/config.py`
- `SecClient` and `FilingCollector` services for SEC discovery, section parsing,
  and annual XBRL metric normalization
- `uv` dependency management and a small API test suite

## Quick start

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --dev
cp .env.example .env.development
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
SEC_FILING_AGENT_SEC_USER_AGENT="sec-filing-agent/0.1 your-email@example.com"
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

## SEC service layer

The SEC collector deliberately has no FastAPI dependency. Create the client in
your route dependency or application lifespan, then inject it into the collector:

```python
from sec_filing_agent.services.filing_collector import FilingCollector
from sec_filing_agent.services.sec_client import SecClient

async with SecClient("sec-filing-agent/0.1 your-email@example.com") as client:
    result = await FilingCollector(client).collect(
        ["AAPL"],
        form_types=["10-K", "10-Q"],
        max_filings_per_ticker=3,
        include_historical=False,
    )
```

`result` contains filing metadata, section text with source locations, annual
XBRL metrics with fact provenance, and best-effort warnings. Build your own
request models, routes, chunking, retrieval, and LLM generation on top of it.

Run checks with:

```bash
uv run ruff check .
uv run pytest
```

### QueryPlanner model regression evaluation

After changing the planner prompt or PlannerOutput schema, run the baseline
evaluation against the real DeepSeek API:

```bash
npm ci
npm run eval:planner
```

See [evals/query_planner/README.md](evals/query_planner/README.md) for the test
cases, grading criteria, and execution requirements.

### OpenSpec development workflow

The Node.js tools require Node 22.22+. Install the locked versions with `npm ci`.
OpenSpec is initialized; its configuration is in `openspec/config.yaml`, and
Codex workflow skills are in `.agents/skills/`.

```bash
npm run openspec -- list
npm run spec:validate
```

In Codex, use `$openspec-propose` to describe a new change,
`$openspec-apply-change` to implement it, and `$openspec-archive-change` to
archive it when complete. Specifications live in `openspec/specs/`, and changes
live in `openspec/changes/`. The existing functionality baseline is organized
into nine capabilities; see the [OpenSpec specification index](openspec/README.md).

Changes to the QueryPlanner prompt, output schema, or model must include the
`npm run eval:planner` baseline evaluation and review of structured fields and
semantic_query.

### Documentation language

Write all project-maintained READMEs in English, including new and updated
nested or extensionless READMEs. Use English for headings, explanatory prose,
and explanatory example comments. OpenSpec main specs, delta specs, and
planning artifacts must also be written in English.

Preserve commands, paths, configuration keys and values, links, and executable
code semantics when translating documentation. Keep intentional multilingual
input examples unchanged and write their surrounding explanations in English.
