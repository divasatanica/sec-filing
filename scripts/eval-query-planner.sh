#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PROMPTFOO_PYTHON="$PWD/.venv/bin/python"
export PROMPTFOO_CONFIG_DIR="$PWD/evals/query_planner/results/promptfoo"
mkdir -p evals/query_planner/results
if [[ ! -x node_modules/.bin/promptfoo ]]; then
  echo "Promptfoo is not installed. Run npm ci first." >&2
  exit 1
fi
node_modules/.bin/promptfoo eval \
  -c evals/query_planner/promptfooconfig.yaml \
  --no-cache \
  -o "evals/query_planner/results/$(date -u +%Y%m%dT%H%M%SZ).json" \
  "$@"
