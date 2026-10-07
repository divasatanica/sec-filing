import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from sec_filing_agent.core.config import Settings
from sec_filing_agent.services.query_planner.planner import (
    PLANNER_SYSTEM_PROMPT,
    QueryPlanner,
)


def run_plan(content, finish_reason="stop"):
    settings = Settings(
        environment="test",
        sec_user_agent="test-agent",
        database_url="postgresql+asyncpg://test:test@localhost/test",
        deepseek_api_key="test-key",
    )
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(content=content),
            )
        ]
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(return_value=response)),
        )
    )
    with patch("sec_filing_agent.services.query_planner.planner.AsyncOpenAI") as constructor:
        constructor.return_value.__aenter__ = AsyncMock(return_value=client)
        constructor.return_value.__aexit__ = AsyncMock(return_value=False)
        plan = asyncio.run(QueryPlanner(settings).plan("AAPL supply chain risks"))
    return plan, client.chat.completions.create


def test_plan_validates_response_and_keeps_query_in_user_message():
    plan, create = run_plan(
        '{"semantic_query":"supply chain risks","tickers":["AAPL"],"report_date_from":"2023-01-01"}'
    )
    assert plan.tickers == ["AAPL"]
    assert plan.report_date_from == date(2023, 1, 1)
    kwargs = create.call_args.kwargs
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["messages"] == [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        {"role": "user", "content": "AAPL supply chain risks"},
    ]


@pytest.mark.parametrize("content,reason", [(None, "stop"), ("", "stop"), ("{}", "length")])
def test_plan_rejects_empty_or_incomplete_response(content, reason):
    with pytest.raises(ValueError):
        run_plan(content, reason)


def test_plan_rejects_invalid_schema():
    with pytest.raises(ValidationError):
        run_plan('{"tickers":["AAPL"]}')
