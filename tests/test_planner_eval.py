"""Offline checks for the evaluator itself; these do not measure model quality."""

import importlib.util
import json
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[1] / "evals" / "query_planner"
spec = importlib.util.spec_from_file_location("planner_eval_assertions", EVAL_DIR / "assertions.py")
assertions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assertions)

CONTEXT = {
    "vars": {
        "expected": {
            "tickers": ["RKLB", "AAPL"],
            "report_date_from": "2099-07-01",
            "report_date_to": "2099-09-30",
        },
        "closed_interval": True,
    }
}
OUTPUT = {
    "semantic_query": "Revenue growth and its drivers",
    "tickers": ["AAPL", "RKLB"],
    "report_date_from": "2099-07-01",
    "report_date_to": "2099-09-30",
}


def test_eval_accepts_expected_fields_and_order_independent_tickers():
    assert assertions.get_assert(json.dumps(OUTPUT), CONTEXT)["pass"]


@pytest.mark.parametrize(
    "changes",
    [
        {"report_date_from": None},
        {"report_date_to": "2099-06-30"},
        {"report_date_from": "2099-08-01"},
        {"semantic_query": " "},
        {"tickers": []},
        {"report_date_from": "invalid"},
    ],
)
def test_eval_rejects_regressions(changes):
    assert not assertions.get_assert(json.dumps(OUTPUT | changes), CONTEXT)["pass"]


def test_eval_rejects_invalid_json():
    assert not assertions.get_assert("not JSON", CONTEXT)["pass"]


def test_eval_rejects_unknown_expected_field():
    with pytest.raises(ValueError, match="Unknown expected field"):
        assertions.get_assert(json.dumps(OUTPUT), {"vars": {"expected": {"typo": None}}})
