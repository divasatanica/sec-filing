# Query Planning Specification

## Purpose
Define natural-language reasoning into structured SEC retrieval plans. Temporal semantics are primarily guided by the prompt; the current Pydantic schema does not enforce closed intervals or date ordering at runtime.

## Requirements

### Requirement: Structured inference and responsibility boundaries
The planner SHALL extract or reasonably infer semantic_query, tickers, form_types, report_date_from/to, and item_codes from user meaning. It SHALL NOT answer financial questions, generate SQL, retrieve documents, or assess filing publication. The user query SHALL be supplied in the user message without overriding system rules.

#### Scenario: Quarterly report request
- **WHEN** the user asks about growth in RKLB's 2026 Q2 quarterly report
- **THEN** the planner infers RKLB and 10-Q and produces a growth-focused semantic_query with the corresponding date filters

### Requirement: Semantic preservation and justified restrictions
semantic_query SHALL prefer English and preserve topics, negation, comparisons, and unfilterable constraints. Company names, forms, and dates MAY be removed only if accurately represented in filters. Tickers SHALL be uppercase; name-to-ticker mapping SHALL be reliable. Section filters SHALL be reliable and retain necessary evidence. Unspecified or genuinely unresolved fields SHALL use null, not empty arrays.

#### Scenario: Unresolved company name
- **WHEN** a request contains a company name that cannot be reliably identified
- **THEN** tickers is null and semantic_query retains the company name

### Requirement: Reporting period normalization and closed intervals
Dates SHALL be inclusive filters on the reporting period end date, not filing_date. YYYY QN SHALL expand to a calendar quarter unless explicitly fiscal. A calendar year SHALL expand from January 1 through December 31. Range searches SHALL provide both boundaries; exact dates SHALL use equal boundaries.

#### Scenario: Third-quarter range
- **WHEN** the user asks how RKLB grew in 2026Q3
- **THEN** report_date_from is 2026-07-01 and report_date_to is 2026-09-30

#### Scenario: Exact reporting period end
- **WHEN** the user specifies a reporting period end of 2026-06-30
- **THEN** both date fields are 2026-06-30

### Requirement: Future periods and unresolved time expressions
Explicit future periods SHALL be parsed normally without returning null because the period has not ended or a filing may not exist. Explicit fiscal periods SHALL be converted only when the relevant fiscal calendar is reliably known. Latest or relative time expressions without sufficient reference information SHALL NOT produce guessed dates; unresolved time requirements SHALL remain in semantic_query.

#### Scenario: Future quarter
- **WHEN** the user asks about RKLB 2099 Q3
- **THEN** the planner returns the closed interval 2099-07-01 through 2099-09-30 regardless of the current date

#### Scenario: Latest report without a time reference
- **WHEN** the user requests the latest quarterly report without a reliable date reference
- **THEN** no dates are guessed and the latest-report meaning is preserved

### Requirement: Model response and configuration validation
The planner SHALL use project DeepSeek settings and the JSON schema generated from PlannerOutput. Empty queries and missing API keys SHALL be rejected before an API call. Missing choices, empty content, or finish_reason other than stop SHALL be rejected. Completed content SHALL pass PlannerOutput.model_validate_json before being returned.

#### Scenario: Truncated model response
- **WHEN** finish_reason is length
- **THEN** an error is raised rather than accepting an incomplete plan

## References
- `src/sec_filing_agent/services/query_planner/planner.py`
- `src/sec_filing_agent/models.py`
- `tests/test_query_planner.py`
- `evals/query_planner/cases.yaml`
