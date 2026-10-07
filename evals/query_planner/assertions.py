"""Deterministic checks for structured fields; semantic wording is not exact-matched."""

import json
import sys
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from sec_filing_agent.models import PlannerOutput


def get_assert(output, context):
    try:
        raw = json.loads(output) if isinstance(output, str) else output
        plan = PlannerOutput.model_validate(raw)
    except (ValueError, TypeError, ValidationError) as exc:
        return {"pass": False, "score": 0, "reason": f"Invalid planner output: {exc}"}

    failures = []
    actual = plan.model_dump(mode="json")
    for field, expected in context["vars"]["expected"].items():
        if field not in actual:
            raise ValueError(f"Unknown expected field: {field}")
        value = actual[field]
        if isinstance(expected, list) and isinstance(value, list):
            matches = sorted(value) == sorted(expected)
        else:
            matches = value == expected
        if not matches:
            failures.append(f"{field}: expected {expected!r}, got {value!r}")

    if context["vars"].get("closed_interval"):
        if plan.report_date_from is None or plan.report_date_to is None:
            failures.append("Range search requires both date boundaries")
    if plan.report_date_from and plan.report_date_to:
        if plan.report_date_from > plan.report_date_to:
            failures.append("Date boundaries are reversed")
    if not plan.semantic_query.strip():
        failures.append("semantic_query is empty")
    for field in ("tickers", "form_types", "item_codes"):
        if actual[field] == []:
            failures.append(f"{field}: use null instead of an empty array")

    return {
        "pass": not failures,
        "score": 0 if failures else 1,
        "reason": "; ".join(failures) if failures else "All structured-field checks passed",
    }
