# Tasks

## 1. English README content

- [x] 1.1 Translate Chinese headings, prose, and explanatory comments in `README.md`; verify the diff preserves commands, paths, links, configuration, and executable example semantics.
- [x] 1.2 Translate `evals/query_planner/README.md` into English; verify evaluation instructions, grading boundaries, version information, and intentional multilingual inputs retain their meaning.
- [x] 1.3 Review `openspec/README.md` and `alembic/README`, plus any newly added maintained README files, for English compliance; verify all maintained README headings and explanatory content are English without editing dependency or generated files.
- [x] 1.4 Add concise English contributor guidance to the root README describing the README and OpenSpec language policy; verify it covers future additions and updates and preserves multilingual input examples.

## 2. OpenSpec language guidance

- [x] 2.1 Extend the language context in `openspec/config.yaml` to explicitly require English project-maintained READMEs, main specs, delta specs, and planning artifacts; verify the YAML remains readable by OpenSpec and unrelated context and rules are preserved.
- [x] 2.2 Review current main specs and active change artifacts for English explanatory content and headings; verify existing specification requirements remain intact and correct any language-only omissions without altering historical archives.

## 3. Integrated validation

- [x] 3.1 Run `npm run openspec -- validate english-readme-policy --strict` and `npm run spec:validate`; verify all validations pass and manually review the combined documentation diff for language consistency and semantic preservation. Documentation-only changes require no live DeepSeek evaluation.

## Workflow follow-up

- After implementation is reviewed, use openspec-sync-specs for english-readme-policy to merge the developer-workflow delta into main specs and validate the synchronized specs.
- Archive the completed change with openspec-archive-change; retain the archived artifacts as decision history.
