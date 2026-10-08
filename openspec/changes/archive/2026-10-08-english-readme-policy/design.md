# Design

## Context

See proposal.md for motivation. The tracked README inventory is `README.md`, `evals/query_planner/README.md`, `openspec/README.md`, and `alembic/README`. The first two contain Chinese guidance; the others already use English. The developer-workflow spec and OpenSpec context already require English specs and planning artifacts. The evaluation dataset intentionally contains Chinese and English inputs.

## Goals / Non-Goals

**Goals:** Make the language boundary precise across documentation and OpenSpec guidance while preserving runnable examples and multilingual evaluation coverage.

**Non-Goals:** Translate historical archived changes, internal historical documents, evaluation datasets, application prompts, or vendored/generated dependency documentation. Add no language-detection dependency or runtime behavior change.

## Decisions

- Use the existing developer-workflow capability for the README policy and extend its existing specification-maintenance requirement. This keeps related contributor conventions together; a separate documentation capability would duplicate the current boundary.
- Review all four maintained READMEs, translating only content that needs it. Match future README names case-insensitively, with or without extensions, in maintained project directories. Exclude third-party dependency trees and generated tool output because the project does not author those files.
- Translate natural-language example comments, but preserve commands, identifiers, paths, URLs, configuration values, and executable statements. Retain intentional multilingual input literals with English surrounding explanations. Translating input data would change evaluation meaning.
- Extend the existing language lines in `openspec/config.yaml` without replacing unrelated context or rules. Review main specs and active planning artifacts for English compliance; preserve historical archives as decision history. The existing main specs already appear to follow the policy.
- Use manual semantic review and OpenSpec validation. A blanket non-ASCII check would reject valid input examples and punctuation; automated language classification adds unnecessary dependencies for this documentation change.

## Risks / Trade-offs

- Translation changes operational guidance → Compare commands, links, configuration, and code examples against the original diff.
- Future contributors miss the policy → Document it in contributor-facing README guidance, the developer-workflow contract, and OpenSpec context.
- Documentation is structurally valid but mistranslated → Review meaning manually; OpenSpec validation checks structure rather than English fluency.

## Migration Plan

Translate maintained README content and update language context during apply. Validate the active delta and review existing main specs for English compliance. Sync the developer-workflow delta after implementation, then archive the change when complete. Roll back only this change's documentation and context edits if needed, preserving unrelated working-tree changes.
