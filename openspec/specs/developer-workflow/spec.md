# Developer Workflow Specification

## Purpose
Define model regression evaluation, reproducible developer dependencies, and OpenSpec maintenance conventions based on the existing tooling and confirmed project practices.

## Requirements

### Requirement: Reproducible developer tool dependencies
The project SHALL declare a private developer tooling package in package.json, lock Promptfoo and OpenSpec dependencies in package-lock.json, and install them with npm ci. node_modules and local evaluation results SHALL NOT be committed to Git. Python execution SHALL use the project .venv.

#### Scenario: Installing tools in a new environment
- **WHEN** a developer has prepared Python and a Node version satisfying engines
- **THEN** npm ci installs the tools needed for npm run eval:planner and npm run openspec

### Requirement: Separate live planner evaluations and offline tests
Model evaluations SHALL live in evals/query_planner and use a Python provider that directly calls the production QueryPlanner without copying its prompt, schema, or API parameters. Evaluations SHALL NOT depend on FastAPI, the database, or embeddings. tests/ SHALL retain mocked unit tests and offline evaluator checks.

#### Scenario: Updating field descriptions
- **WHEN** an evaluation runs after a PlannerOutput description change
- **THEN** the request uses the schema currently generated from code rather than a separately maintained schema copy

### Requirement: Grading and evaluation boundaries
The baseline SHALL cover quarter expressions, future periods, closed ranges, exact dates, leap years, multiple companies, and unspecified or unresolved dates. expected SHALL constrain only declared fields, compare lists without regard to order, and compare dates exactly. Assertions SHALL check nonempty semantic_query, date ordering, and empty-array conventions without exact matching of free text.

#### Scenario: Valid English paraphrase
- **WHEN** semantic_query uses different wording while structured fields are correct
- **THEN** wording alone does not fail the evaluation; topics, comparisons, incorrect quarters, and additional meaning are reviewed manually

### Requirement: Uncached execution and version tracking
npm run eval:planner SHALL disable Promptfoo caching, call the real DeepSeek API sequentially by default, and write UTC-timestamped JSON reports and local tool state to an ignored directory. Output metadata SHALL retain the model name and SHA-256 hashes of the prompt and schema. Repetition SHALL be configurable through --repeat.

#### Scenario: Checking model stability
- **WHEN** npm run eval:planner -- --repeat 3 is executed
- **THEN** each baseline question is evaluated three times through live calls instead of reusing cached output

### Requirement: Planner regressions and specification maintenance
Planner prompt, schema, description, or model changes SHALL trigger baseline execution and review of failures and semantic_query. New defects SHALL enter the dataset; expectations SHALL NOT change solely to pass evaluations. OpenSpec SHALL maintain current specs by capability and use changes for future behavior. Documentation-only edits SHALL NOT require live model calls. OpenSpec main specs, delta specs, and planning artifacts SHALL be written in English.

#### Scenario: Quarter parsing regression
- **WHEN** a real request produces an incorrect date or null
- **THEN** a reproducible case is added, and regression evaluation checks the fix and other failures

#### Scenario: Authoring or updating specifications
- **WHEN** a contributor creates or updates OpenSpec main specs, delta specs, or planning artifacts
- **THEN** headings and explanatory content are in English, including structural headings and SHALL/MUST keywords

#### Scenario: Maintaining language guidance
- **WHEN** OpenSpec project language context is maintained
- **THEN** it explicitly requires English project-maintained READMEs, main specs, delta specs, and planning artifacts

### Requirement: English README documentation
All project-maintained README files, including extensionless and nested READMEs, SHALL use English for headings, explanatory prose, and explanatory example comments. New and updated README content SHALL follow this policy. Translation SHALL preserve commands, paths, configuration keys and values, links, and executable code semantics; intentional multilingual input examples SHALL retain their original text.

#### Scenario: Translating existing READMEs
- **WHEN** existing project-maintained READMEs contain non-English explanatory content
- **THEN** that content is translated into English while commands, paths, configuration, links, and executable code retain their meaning

#### Scenario: Creating or updating a README
- **WHEN** a contributor creates or updates a project-maintained README anywhere in the repository
- **THEN** the resulting explanatory prose, headings, and explanatory example comments are in English

#### Scenario: Preserving multilingual evaluation inputs
- **WHEN** a README includes an intentional non-English input example for multilingual evaluation
- **THEN** the input remains unchanged and its surrounding explanation is in English

## References
- `package.json`, `package-lock.json`
- `scripts/eval-query-planner.sh`
- `evals/query_planner/`
- `tests/test_planner_eval.py`
- `openspec/config.yaml`
