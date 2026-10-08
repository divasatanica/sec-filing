# QueryPlanner baseline evaluation

This directory uses Promptfoo to call the real DeepSeek API and evaluate the
QueryPlanner in production code. FastAPI, a database, and an embedding model
are not required. Regular mocked unit tests remain in tests/.

## Running the evaluation

At the project root, prepare the Python .venv (uv sync) and Node.js/npm, then
run npm ci. Set SEC_FILING_AGENT_DEEPSEEK_API_KEY in the existing
.env.development file. The model and base URL also use the project Settings.
Do not put API keys in evaluation configuration or test cases.

```bash
npm run eval:planner
# Repeat evaluations for significant changes to check stability:
npm run eval:planner -- --repeat 3
```

The script uses the project .venv, disables Promptfoo caching, calls the real
API sequentially, and saves UTC-timestamped JSON results to results/. Promptfoo
local state is also stored there; the entire directory is excluded from Git.
Promptfoo is managed as a package.json development dependency pinned to 0.124.0;
package-lock.json locks the full dependency tree. Revalidate the baseline when
upgrading the tool.

provider.py calls QueryPlanner.plan() directly without copying the prompt,
schema, or API parameters. Output metadata records the model name and SHA-256
hashes of the prompt and schema to track evaluation versions. Caching must be
disabled because the prompt/schema are inside the provider.

## Baseline and grading

cases.yaml contains 36 fixed cases (19 Chinese and 17 English), covering calendar
quarters, alternative wording, future dates, full years, first halves of years,
ranges spanning years, exact dates, leap years, multiple companies, and
unspecified or unresolved dates. expected lists only the fields that require
exact checks for each case; omitted fields need not match a snapshot. Lists
are compared without regard to order, dates are compared exactly, and range
cases must provide both bounds. Cases using 2099 keep future-period coverage
independent of the evaluation date.

assertions.py also validates the current PlannerOutput schema, nonempty
semantic_query, date ordering, and empty-array conventions. These assertions
apply only to evaluation and add no restrictions to the production planner.
Topic preservation, year-over-year comparisons, incorrect quarters, and
unrelated topics in semantic_query still require manual review. Passing
structured-field checks does not establish retrieval quality; free text is
not compared against full-text snapshots.

Run this suite after changing the prompt, field descriptions, schema, or model.
Compare the overall pass rate and failing cases. Investigate API/connection
errors separately from semantic parsing errors. Add cases for real defects;
do not update expected fields solely to make tests pass. The case set is not
intended to enumerate every real request and should grow over time.

Regular unit tests verify request construction, response parsing, and exception
handling; this evaluation verifies model understanding. Both are needed.

Reference: https://www.promptfoo.dev/docs/providers/python/
