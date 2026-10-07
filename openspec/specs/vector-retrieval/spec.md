# Vector Retrieval Specification

## Purpose
Define existing embedding indexing and cosine retrieval with metadata filters. This baseline does not claim hybrid search, reranking, or answer generation capabilities.

## Requirements

### Requirement: Model profiles and vector derivation
Embeddings SHALL be stored separately, uniquely identified by (chunk_id,model_profile_id), and retain CIK and source_content_hash. Model profiles SHALL include model_name, revision, and dimensions. The current service SHALL use profile ID 1 and normalized 1024-dimensional vectors from local Qwen3-Embedding-4B, preferring available MPS and otherwise CPU.

#### Scenario: Document and query encoding
- **WHEN** documents or queries are encoded
- **THEN** documents are encoded directly, queries use the investor SEC passage retrieval instruction, and the model loads locally on first use

### Requirement: Idempotent index updates
Index construction SHALL scope chunks to one CIK and raise ChunkNotFoundError when no chunks exist. force=false SHALL encode only missing vectors or changed source_content_hash values. force=true SHALL re-encode all target chunks and upsert by the unique key.

#### Scenario: Current index
- **WHEN** all existing vector hashes match chunk content hashes and processing is not forced
- **THEN** indexing returns 0 without re-encoding

### Requirement: Plan-driven query filtering
POST /embeddings/search SHALL call the planner, map its tickers to CIKs through local CompanyService, encode semantic_query, and apply non-null CIK, form, report_date, and item conditions to SQL. Missing planner tickers SHALL return 400. Responses SHALL include plan and results. top_k SHALL use the request value, default to 5, and accept 1–100.

#### Scenario: Requested quarter and result count
- **WHEN** the planner supplies 2026 Q2 boundaries and the caller requests top_k=3
- **THEN** filtering uses report_date >= 2026-04-01 and <= 2026-06-30 and returns at most three results

### Requirement: Cosine ranking and citable evidence
Retrieval SHALL constrain one model_profile_id, order by ascending cosine distance, and compute score as 1-distance. Results SHALL include chunk_id, score, CIK, accession, form_type, report_date, item_code, content, and source_url. Scores SHALL NOT be interpreted as probabilities of answer correctness.

#### Scenario: No matching vectors
- **WHEN** SQL conditions match no results
- **THEN** results is empty and no financial conclusion is generated

### Requirement: Boundary context restoration
After retrieval, truncated sentences or lines SHALL be repaired only from adjacent chunks with the same cleaning_id, preserving chunk_id, score, and rank. Unreliable overlaps or boundaries SHALL NOT be guessed, and stored text SHALL NOT change.

#### Scenario: Hit starts within a sentence
- **WHEN** the previous chunk provides reliable overlap and a recoverable boundary
- **THEN** only returned content is expanded and the original hit's score and ranking remain unchanged

### Requirement: Background index endpoint
POST /embeddings/tickers/{ticker}/index SHALL resolve the local CIK, schedule indexing through FastAPI BackgroundTasks, and return ticker, queued, and job_id. job_id SHALL identify the returned task without claiming persistent job status queries.

#### Scenario: Submitting an index request
- **WHEN** the ticker maps to a local CIK
- **THEN** a queued response is returned and build_embedding_index executes in the background

## References
- `src/sec_filing_agent/api/routes/embeddings.py`
- `src/sec_filing_agent/services/company_service.py`
- `src/sec_filing_agent/services/embedding/`
- `src/sec_filing_agent/db/tables.py`
- `tests/test_embedding_tables.py`
