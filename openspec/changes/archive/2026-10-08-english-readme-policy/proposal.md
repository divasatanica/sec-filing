# Proposal

## Why

Project READMEs currently mix English and Chinese, while OpenSpec already requires English specifications and planning artifacts. A consistent English documentation policy will make contributor guidance accessible and prevent future README updates from reintroducing mixed-language prose.

## What Changes

- Translate non-English headings, explanatory prose, and explanatory code comments in project-maintained READMEs into English.
- Cover `README.md`, `evals/query_planner/README.md`, `openspec/README.md`, and the extensionless `alembic/README`; retain already-English content where appropriate.
- Add an ongoing English README requirement and explicit specification-authoring scenarios to `developer-workflow`.
- Extend `openspec/config.yaml` language context to include READMEs while retaining English requirements for main specs, delta specs, and planning artifacts.
- Preserve command behavior, paths, configuration keys and values, code semantics, and intentional multilingual evaluation inputs.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `developer-workflow`: Require English project-maintained READMEs and explicitly verify English OpenSpec specifications and planning artifacts during maintenance.

## Impact

Documentation and OpenSpec language guidance only. No application behavior, API, dependency, planner prompt, schema, evaluation dataset, or historical archive changes are proposed. Validation uses documentation review and OpenSpec checks; live model calls are unnecessary.
