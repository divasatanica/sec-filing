# Project Specification Index

This directory records the current SEC Filing Agent baseline. Specifications are grounded in the code, tests, configuration, and confirmed project conventions at the time of documentation, including implemented changes that have not yet been committed. This is documentation of existing behavior, not a new feature implementation; historical SOP recommendations are not all treated as delivered capabilities.

## Capability Specifications

| Capability | Scope | Main implementation sources |
| --- | --- | --- |
| [api-runtime](specs/api-runtime/spec.md) | Configuration, route separation, request identifiers, safe error responses | main, config, middleware, routes |
| [sec-collection](specs/sec-collection/spec.md) | Rate limiting, retries, CIKs, filing selection, history, document fallbacks | sec_client, filing_collector |
| [filing-parsing](specs/filing-parsing/spec.md) | Form sections, body heading selection, boundaries, offsets, truncation | filing_parser |
| [xbrl-facts](specs/xbrl-facts/spec.md) | Annual metrics, fact selection, units, provenance, derived metrics | xbrl |
| [ingestion-persistence](specs/ingestion-persistence/spec.md) | Stable identities, idempotency, filing transactions, auditing, migrations | ingestion_service, tables, Alembic |
| [corpus-preparation](specs/corpus-preparation/spec.md) | Raw text preservation, cleaning, invalidation, token budgets, numeric atoms | cleaning_service, chunking_service |
| [query-planning](specs/query-planning/spec.md) | Reasonable inference, future periods, closed intervals, response validation | planner, PlannerOutput |
| [vector-retrieval](specs/vector-retrieval/spec.md) | Profiles, embedding updates, filtering, ranking, context restoration | embeddings route, embedding_service |
| [developer-workflow](specs/developer-workflow/spec.md) | Dependencies, live model baselines, grading, maintenance conventions | package.json, evals, runner script |

Each specification contains Requirements, verifiable Scenarios, and source References. Reference paths are relative to the repository root. A scenario defines a contract; it does not imply that every scenario already has an automated test. Specifications and planning artifacts are written in English; evaluation inputs may remain multilingual to cover actual user queries.

## Historical Documents

- `internal-docs/INTEGRATION_SOP.md` is a design reference for migrating the older TypeScript collector to Python. This baseline uses current Python sorting, fallbacks, and parsing rather than restoring shortcomings of the source implementation as requirements.
- `internal-docs/v1.md` is the early NVDA three-10-K database/RAG roadmap. Current code supports multiple tickers, planning, and vector retrieval; this baseline does not retain that roadmap's single-company or pre-LLM phase boundaries.
- Historical documents remain unchanged, and internal-docs is currently ignored by Git. Current contracts live in version-controlled specs; subsequent behavior changes are maintained through changes.

## Known Differences and Unimplemented Scope

- `tests/test_embedding_routes.py` still expects 501 responses from embedding endpoints, but those endpoints now implement indexing and search. That stale test is not the current API contract and should be updated in a separate code change.
- Retrieval currently uses SQL metadata filters and cosine ranking. Full-text search, hybrid search, reranking, and evidence-based answer generation remain planned capabilities from the older SOP.
- Closed intervals, future dates, and reasonable inference are guided by planner prompt/schema descriptions and evaluated through live model baselines. Pydantic does not currently reject one-sided or reversed date intervals at runtime.
- Search has no preliminary filing-existence check. Empty results indicate no retrieval match, not proof that SEC has not published the report.
- SearchRequest accepts ticker, but search uses planner.tickers and does not implement a separate payload.ticker override.
- CompanyService does not explicitly report partial failures when resolving multiple tickers. Missing mappings may lead to a generic search 500; the baseline does not promise dedicated missing-company or missing-report status codes.
- Indexing returns queued/job_id but has no persistent task queue or job status endpoint.
- XBRL extracts annual FY metrics; the baseline does not claim quarterly extraction, strict duration selection, or matching-period validation of free cash flow inputs.
- Cleaning currently maintains one mutable cleaning per section, not concurrent cleaner_version variants.
- Rate-limiter locks belong to a client's limiter, not a shared service-wide or cross-process limiter.

## Maintenance and Validation

```bash
npm run spec:validate
npm run openspec -- list --specs
```

Use the OpenSpec proposal, apply, sync, and archive workflow for future behavior changes. This initial documentation baseline does not create a pending change for behavior that is already implemented.

Planner prompt, schema, or model changes also require `npm run eval:planner`. Documentation-only organization does not require additional DeepSeek calls.

## Version Control

Commit `openspec/specs/`, `openspec/config.yaml`, this index, active change artifacts, and archived changes to Git and GitHub alongside the relevant code. Review specifications and implementation together in pull requests. Preserve archived changes as decision history.

Commit the generated project OpenSpec skills in `.agents/skills/` and the CLI dependency manifests so contributors can reproduce the workflow. Keep credentials, node_modules, and local evaluation results out of Git.

Commit a proposal when sharing it for review; synchronize the main specifications when the implemented behavior is ready to become the current contract. Git provides history for both planning and delivered behavior.
