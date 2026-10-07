# XBRL Facts Specification

## Purpose
Define annual companyfacts metric selection, provenance retention, and derived metric rules. This baseline does not claim quarterly XBRL extraction capabilities.

## Requirements

### Requirement: Annual fact normalization
The extractor SHALL select facts with supported annual forms and fp=FY, support US GAAP, IFRS, and mappable custom namespaces, and return at most the latest three fiscal years by default. Missing or unsupported companyfacts SHALL produce empty metrics and warnings.

#### Scenario: No mappable annual facts
- **WHEN** companyfacts has no valid annual metrics
- **THEN** fiscal_metrics is empty and the missing or unsupported reason is recorded

### Requirement: Deterministic fact selection and provenance
For multiple facts of an annual metric, the extractor SHALL prefer accessions from selected_filings, then prioritize frame, filed, end, and start. Each MetricValue SHALL retain unit, dates, accession, namespace, concept, form, fiscal_period, frame, and derived.

#### Scenario: Selected amendment and competing annual facts
- **WHEN** an amendment accession belongs to selected_filings
- **THEN** its candidate facts are preferred and their provenance is retained

### Requirement: Fact periods and fiscal year containers
The system SHALL treat fiscal_year as grouping information and express provenance and actual periods through each fact's accession, start_date, end_date, and unit. It SHALL NOT assume all metrics in one fiscal year container originate from the same filing or period.

#### Scenario: Same-year metrics from different accessions
- **WHEN** two metrics share a fiscal year but have different source accessions
- **THEN** each retains its provenance and is grouped by its own accession during ingestion

### Requirement: Unit constraints for derived metrics
When primary revenue/costOfRevenue is absent, the extractor SHALL fill it from existing contract-revenue/goods-and-services-cost aliases. freeCashFlow SHALL be derived only when operatingCashFlow and capex both exist with equal units, using operatingCashFlow minus abs(capex) and marking derived.

#### Scenario: Incompatible cash flow and capex units
- **WHEN** operatingCashFlow uses USD and capex uses EUR
- **THEN** freeCashFlow is not generated

## References
- `src/sec_filing_agent/services/xbrl.py`
- `src/sec_filing_agent/models.py`
- `tests/test_xbrl.py`
