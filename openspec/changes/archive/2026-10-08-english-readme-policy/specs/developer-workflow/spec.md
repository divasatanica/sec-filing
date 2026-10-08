# Spec Delta

## ADDED Requirements

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

## MODIFIED Requirements

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
