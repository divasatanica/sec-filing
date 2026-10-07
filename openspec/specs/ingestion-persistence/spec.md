# Ingestion Persistence Specification

## Purpose
Define auditable, idempotent SEC data persistence with per-filing transaction boundaries, stable identities, fact provenance, and database-maintained company scope.

## Requirements

### Requirement: Stable identities and idempotent writes
The system SHALL identify companies by CIK, ticker relationships by (ticker,cik), filings by accession_number, and raw sections by (accession,item_code,parser_version). Amendments SHALL retain independent accessions. Reingestion SHALL update data with the same identity rather than create duplicate rows.

#### Scenario: Reingesting a filing
- **WHEN** the same accession and section identity already exist
- **THEN** metadata and raw text hashes are updated without creating a duplicate filing

### Requirement: Atomic per-filing commits
IngestionService SHALL write each filing's company, ticker, filing, sections, and matching financial facts in one transaction. Handled persistence failures for one filing SHALL produce warnings and allow other filings to continue.

#### Scenario: Filing persistence failure
- **WHEN** one filing encounters SQLAlchemyError, ValueError, or ArithmeticError
- **THEN** partial writes from that transaction are not retained, other filings continue, and the failed accession is recorded

### Requirement: Financial fact identity and provenance
Financial facts SHALL use a stable hash identity from accession, metric_key, unit, start_date, end_date, and concept, including placeholders for null values. Numeric changes SHALL NOT alter that identity. Persistence SHALL use Decimal(str(value)) and retain source fields and provenance JSON. Facts without an accession or outside selected filings SHALL NOT be inserted and SHALL produce warnings.

#### Scenario: Revised fact value
- **WHEN** the value of an existing fact identity changes
- **THEN** the existing fact is updated without creating a new identity based on its value

### Requirement: Ingestion run auditing
The system SHALL commit a running ingestion_run before SEC network calls. Completion SHALL persist counts, warnings, finished_at, and completed/partial_failure status. An overall collection exception SHALL mark runs failed and record its exception type.

#### Scenario: Collection completes with warnings
- **WHEN** filing processing finishes with a nonempty warning list
- **THEN** the run is marked partial_failure and successful counts and warning details are saved

### Requirement: Database migrations and derived company scope
SQLAlchemy models and Alembic migrations SHALL manage the database schema. financial_facts, filing_chunks, and chunk_embeddings SHALL store directly queryable CIKs. Migration-defined database triggers SHALL maintain that scope from the owning filing or chunk.

#### Scenario: Company-scoped derived data
- **WHEN** a chunk or financial fact is written
- **THEN** the application writes the owning company's CIK and the database maintains consistency through parent relationships

## References
- `src/sec_filing_agent/services/ingestion_service.py`
- `src/sec_filing_agent/db/tables.py`
- `alembic/versions/`
- `tests/test_ingestion_service.py`
- `tests/test_embedding_tables.py`
