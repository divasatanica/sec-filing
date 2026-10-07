# Corpus Preparation Specification

## Purpose
Define conservative cleaning and token chunk derivation from raw sections, including observable processing behavior, invalidation boundaries, and contracts that subsequent changes must preserve.

## Requirements

### Requirement: Raw text preservation and conservative cleaning
Cleaning SHALL write separate filing_section_cleanings without overwriting content_raw. It SHALL remove only recognized page furniture, normalize whitespace, and preserve repeated table and narrative content. Empty text and short financial statement cross-references matching configured rules SHALL be marked non-indexable with exclusion_reason and cleaning metadata.

#### Scenario: Repeated table rows
- **WHEN** raw text contains valid table rows with identical text
- **THEN** cleaning does not globally deduplicate those rows by text

### Requirement: Idempotent cleaning and downstream invalidation
An existing cleaning SHALL be skipped when source_content_hash is unchanged and force=false. A changed source hash or forced cleaning SHALL update the cleaning and delete its existing chunks. Foreign-key cascades SHALL delete embeddings belonging to those chunks.

#### Scenario: Forced cleaning rebuild
- **WHEN** force=true and a cleaning already exists
- **THEN** derived text is updated, old chunks are deleted, and invalidated_chunks is reported

### Requirement: Section boundaries and token budgets
Chunking SHALL generate chunks only from indexable cleanings and SHALL NOT cross cleaning or section boundaries. Defaults SHALL be cl100k_base encoding, a 500-token budget, and 80-token overlap. Nonempty lines SHALL be combined; oversized lines SHALL be split by sentence first and by tokens when necessary.

#### Scenario: Normal text exceeds the budget
- **WHEN** adding the next unit would exceed 500 tokens
- **THEN** the current chunk is finalized and the next chunk retains up to the configured overlap when its budget permits

### Requirement: Numeric atoms and content tracking
Splitting SHALL avoid bisecting comma-separated numeric atoms. A protected atom larger than the budget SHALL remain intact, allowing that exceptional chunk to exceed the budget. Chunks SHALL retain cleaning_id, CIK, sequential index, content, token_count, and a SHA-256 content hash.

#### Scenario: Oversized protected number
- **WHEN** a complete numeric atom exceeds the token budget
- **THEN** its integrity is preserved rather than splitting the numeric value to satisfy the budget

### Requirement: Chunk rebuild prerequisites
Missing raw sections SHALL raise CorpusNotFoundError; raw sections without cleanings SHALL raise CleaningsNotFoundError. Existing chunks SHALL be skipped when force=false and deleted and rebuilt when force=true. Non-indexable cleanings SHALL be skipped.

#### Scenario: Previously chunked section
- **WHEN** a cleaning already has chunks and processing is not forced
- **THEN** no duplicate chunks are written and skipped_sections is reported

## References
- `src/sec_filing_agent/services/cleaning_service.py`
- `src/sec_filing_agent/services/chunking_service.py`
- `tests/test_cleaning_service.py`
- `tests/test_chunking_service.py`
