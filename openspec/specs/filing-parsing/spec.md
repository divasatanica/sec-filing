# Filing Parsing Specification

## Purpose
Define traceable section extraction from SEC HTML and complete submission text, including form-specific headings, document boundaries, normalized offsets, and truncation behavior.

## Requirements

### Requirement: Form-specific section recognition
The parser SHALL use form-specific section rules covering 10-K, 10-Q, 8-K, 20-F/40-F, 6-K, and proxy filing families with configured amendment variants. 10-Q SHALL distinguish Part I and Part II rather than reuse 10-K section semantics.

#### Scenario: Quarterly report parsing
- **WHEN** a 10-Q contains Part I Items 1 and 2
- **THEN** financial statements and MD&A are recorded as `part_i_item_1` and `part_i_item_2`, respectively

### Requirement: Body heading selection and section boundaries
The parser SHALL use line-anchored heading rules. Multiple valid matches for a heading SHALL select the last match and produce a duplicate-heading warning. A section SHALL end at the next formal section heading even when that heading is not an extraction target.

#### Scenario: Duplicate headings in the table of contents and body
- **WHEN** the table of contents and body contain the same valid Item heading
- **THEN** the later body heading is selected instead of treating the table of contents entry as the section body

#### Scenario: Following section is not an extraction target
- **WHEN** Item 1A is followed by an unselected Item 1B
- **THEN** Item 1A ends before that formal heading and does not absorb Item 1B

### Requirement: Readable text and location metadata
The parser SHALL remove script/style content, decode entities, preserve text block and table row boundaries, and output filing accession, form, report_date, item_code, label, actual source_url, document_kind, source_start/source_end, and truncated. Offsets SHALL refer to normalized text rather than raw HTML bytes.

#### Scenario: Parsing table content
- **WHEN** HTML contains tables and paragraphs
- **THEN** output retains recognizable row and paragraph boundaries together with source and location metadata

### Requirement: Preview truncation and complete ingestion
The parser SHALL limit each section to 15,000 characters by default and record truncated and a truncation marker. max_chars=None SHALL preserve the complete section. Missing sections, unusually short sections, and unsupported forms SHALL produce warnings.

#### Scenario: Durable ingestion
- **WHEN** IngestionService invokes the collector
- **THEN** section_max_chars=None is used so preview limits do not truncate persisted raw text

## References
- `src/sec_filing_agent/services/filing_parser.py`
- `src/sec_filing_agent/models.py`
- `tests/test_filing_parser.py`
