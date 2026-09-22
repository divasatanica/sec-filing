# SEC Filing Agent

This is a FastAPI service skeleton for a local bot that researches US-listed
instruments using SEC filings and material 8-K events.

```text
SEC EDGAR / news source → Filing gateway → Repository → Parser / chunker → RAG engine → HTTP API
```

The project already provides a stable HTTP contract, configuration loading,
dependency injection, error mapping, and tests. SEC downloads, XBRL/HTML
parsing, 8-K item extraction, vectorization, vector storage, and answer
generation are deliberately left for you to implement.

## Quick start

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --dev
cp .env.example .env
uv run uvicorn sec_filing_agent.main:app --reload
```

The service binds to `127.0.0.1:8000` by default, so it is accessible only
from the local machine. Interactive API docs are available at
`http://127.0.0.1:8000/docs`; the OpenAPI document is at
`http://127.0.0.1:8000/openapi.json`.

Alternatively, use the production-style entry point:

```bash
uv run sec-filing-agent
```

Run validation and static checks with:

```bash
uv run pytest
uv run ruff check .
```

## API surface

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Verify that the service is running. |
| `POST` | `/v1/filings/sync` | Discover, store, and index filings for one or more instruments. |
| `GET` | `/v1/instruments/{ticker}/filings` | List locally known filing metadata. |
| `GET` | `/v1/filings/{accession_number}` | Get metadata for one filing. |
| `POST` | `/v1/research/query` | Retrieve RAG citations filtered by ticker, form, and date range. |

For example:

```bash
curl -X POST http://127.0.0.1:8000/v1/research/query \
  -H 'content-type: application/json' \
  -d '{
    "query": "What were the material drivers of revenue growth?",
    "filters": {"instruments": ["AAPL"], "forms": ["10-K", "10-Q"]},
    "top_k": 8
  }'
```

Before you connect real adapters, business endpoints return `501` with
`core_not_configured`. This prevents a bot from treating an unconfigured
component as an empty search result. `/health`, `/docs`, and OpenAPI are
available immediately. `/v1/filings/sync` is currently synchronous; if an
ingestion run becomes long-lived, replace its API-level execution with a job
queue while retaining the same service interface.

## Where to implement the core logic

1. Keep the three interfaces in `src/sec_filing_agent/services/contracts.py` stable and implement:
   - `SecFilingsGateway`: Call SEC submissions/archives, respect rate limits, and send `SEC_USER_AGENT`.
   - `FilingRepository`: Store filing metadata, raw-document locations, and processing state in SQLite or Postgres.
   - `RagEngine`: Clean documents, create chunks and embeddings, perform vector search, and return citations with the accession number.
2. In `src/sec_filing_agent/services/container.py`, replace the `Placeholder*` adapters in `build_container()` with your implementations.
3. `IngestionService` already orchestrates **discover → persist → download → index**. Add retries, deduplication, a job queue, or incremental-update behavior there without changing the API layer.

Keep SEC rate limiting, cache keys, and raw-document hashes in the gateway or
repository layer. Every RAG answer should preserve its `instrument`, `form`,
`accession_number`, and source chunk text as an auditable citation.
