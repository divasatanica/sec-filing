"""Evaluate the production planner, without copying its prompt or API settings."""

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from sec_filing_agent.models import PlannerOutput
from sec_filing_agent.services.query_planner.planner import PLANNER_SYSTEM_PROMPT, QueryPlanner


async def call_api(prompt, options, context):
    planner = QueryPlanner()
    output = await planner.plan(prompt)
    return {
        "output": output.model_dump_json(),
        "metadata": {
            "model": planner.settings.deepseek_model,
            "prompt_sha256": hashlib.sha256(PLANNER_SYSTEM_PROMPT.encode()).hexdigest(),
            "schema_sha256": hashlib.sha256(
                json.dumps(PlannerOutput.model_json_schema(), sort_keys=True).encode()
            ).hexdigest(),
        },
    }
