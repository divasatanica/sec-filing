# SEC Collection Specification

## Purpose
Define baseline ticker resolution, filing discovery, SEC network requests, and document fetching, including observable failures and contracts to preserve in subsequent changes.

## Requirements

### Requirement: Company identifiers and collection input
The collector SHALL strip, uppercase, and deduplicate tickers, validate nonempty ticker and form lists, and enforce 1–50 filings per ticker. CIKs SHALL use ten digits in data.sec.gov URLs and omit leading zeros in Archives URLs.

#### Scenario: Unknown ticker
- **WHEN** a ticker is absent from the SEC ticker map
- **THEN** that ticker receives empty filings, sections, and xbrl_metrics with a `ticker_not_found` warning, and other tickers continue

### Requirement: Rate limiting and bounded retries
SecClient SHALL use a nonempty User-Agent. Each client's limiter SHALL serialize request pacing with per-domain locks, defaulting to 0.2 seconds for data.sec.gov and 0.6 seconds for www.sec.gov. Network errors, 429, 503, and decode errors SHALL receive at most three retries, preferring a valid Retry-After and otherwise using 2/4/8-second backoff. Retries SHALL also pass through the limiter.

#### Scenario: SEC rate-limit response
- **WHEN** SEC returns 429 with a valid Retry-After
- **THEN** retries wait for that duration, and exhaustion raises SecClientError with URL, status, and attempt count

### Requirement: Filing discovery and form selection
The collector SHALL read recent submissions by default and merge historical submissions only when explicitly enabled, deduplicating by accession. Selection SHALL prefer exact requested forms and apply the count limit in descending filing_date order. Configured foreign issuer form fallbacks SHALL be used only without exact results, with selection_reason and a warning recorded.

#### Scenario: Exact requested form exists
- **WHEN** 10-K is requested and both 10-K and 20-F filings exist
- **THEN** exact matches are selected without mixing in foreign fallback results

### Requirement: Document fetching fallbacks and provenance
The collector SHALL attempt the primary document first, archive index HTML candidates when it is missing or fails, and complete submission text last. Content SHALL retain the actual source_url and document_kind. Failed stages SHALL produce warnings.

#### Scenario: Primary document fetch fails
- **WHEN** primary HTML is unavailable but an archive candidate is accessible
- **THEN** the candidate is parsed as archive_candidate and the primary failure warning is retained

### Requirement: Best-effort collection results
The collector SHALL return filings, sections, xbrl_metrics, and warnings by ticker. Handled failures of one ticker, filing, or history shard SHALL NOT discard other available results. companyfacts failures SHALL preserve already collected filings and sections.

#### Scenario: Historical shard failure
- **WHEN** one submissions file fails during historical collection
- **THEN** recent and other historical data are retained with a failure warning

## References
- `src/sec_filing_agent/services/sec_client.py`
- `src/sec_filing_agent/services/filing_collector.py`
- `tests/test_sec_client.py`
- `tests/test_filing_collector.py`
