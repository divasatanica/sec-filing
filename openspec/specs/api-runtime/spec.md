# API Runtime Specification

## Purpose
Define the existing contracts for service startup, environment configuration, HTTP orchestration, and request observability, based on the current implementation and confirmed project conventions.

## Requirements

### Requirement: Environment configuration and dependency management
The system SHALL load environment variables with the `SEC_FILING_AGENT_` prefix and configuration from `.env.{environment}`. Python dependencies SHALL be managed by uv, and developer CLI tools by npm and its lockfile. Secrets SHALL remain in environment configuration and SHALL NOT be committed to source control.

#### Scenario: Selecting a runtime environment
- **WHEN** Settings is created with a specific environment
- **THEN** the corresponding environment file is loaded, and an unspecified log_json defaults to readable logs in development and JSON logs in other environments

### Requirement: Request identifiers and structured logging
The system SHALL attach `X-Request-ID` to HTTP responses, accept a nonempty caller identifier of at most 128 characters, and generate a UUID otherwise. Request logs SHALL associate the method, path, status code, and duration with that identifier, and clear request context afterward.

#### Scenario: Caller supplies a request identifier
- **WHEN** a request contains a valid `X-Request-ID`
- **THEN** the response returns the same identifier and logs use it

### Requirement: Unhandled exception responses
The system SHALL convert unhandled handler or service exceptions into safe HTTP 500 responses containing `Internal server error` and request_id, and record the exception in logs.

#### Scenario: Unexpected service exception
- **WHEN** a route call raises an unhandled exception
- **THEN** the client receives HTTP 500 and the request identifier without exception implementation details

### Requirement: API and service separation
FastAPI routes SHALL validate input, orchestrate services, and produce responses. SEC collection, ingestion, cleaning, chunking, and planning SHALL retain independent service entry points. `GET /health` SHALL provide a health response. Core processing endpoints SHALL include ingestion, cleanings, chunks, embedding index, search, and planner plan.

#### Scenario: Missing cleaning or chunking prerequisites
- **WHEN** cleaning or chunking is requested without persisted raw sections
- **THEN** the endpoint returns 404; a chunking request with raw sections but no cleanings returns 409 and directs the caller to run cleanings first

## References
- `src/sec_filing_agent/main.py`
- `src/sec_filing_agent/core/config.py`
- `src/sec_filing_agent/api/middleware.py`
- `src/sec_filing_agent/api/routes/`
- `tests/test_api.py`
