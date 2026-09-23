import asyncio

import httpx
import pytest

from sec_filing_agent.services.sec_client import (
    DomainRateLimiter,
    SecClient,
    SecClientError,
    cik_to_10digits,
    cik_to_archive_path,
)


def test_cik_url_representations_are_validated() -> None:
    assert cik_to_10digits("320193") == "0000320193"
    assert cik_to_archive_path("0000320193") == "320193"
    with pytest.raises(ValueError):
        cik_to_10digits("32A193")
    with pytest.raises(ValueError):
        cik_to_10digits("1" * 11)


def test_retry_after_is_honoured_with_mock_transport() -> None:
    async def scenario() -> None:
        calls: list[httpx.Request] = []
        sleeps: list[float] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(429, headers={"Retry-After": "7"}, request=request)
            return httpx.Response(200, json={"ok": True}, request=request)

        async def record_sleep(delay: float) -> None:
            sleeps.append(delay)

        limiter = DomainRateLimiter({"data.sec.gov": 0}, sleep=record_sleep)
        async with SecClient(
            "test-agent test@example.com",
            transport=httpx.MockTransport(handler),
            rate_limiter=limiter,
            sleep=record_sleep,
        ) as client:
            assert await client.get_json("https://data.sec.gov/example.json") == {"ok": True}

        assert len(calls) == 2
        assert calls[0].headers["user-agent"] == "test-agent test@example.com"
        assert calls[0].headers["accept"] == "application/json"
        assert sleeps == [7.0]

    asyncio.run(scenario())


def test_network_errors_retry_with_exponential_backoff() -> None:
    async def scenario() -> None:
        sleeps: list[float] = []

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        async def record_sleep(delay: float) -> None:
            sleeps.append(delay)

        limiter = DomainRateLimiter({"data.sec.gov": 0}, sleep=record_sleep)
        async with SecClient(
            "test-agent test@example.com",
            transport=httpx.MockTransport(handler),
            max_retries=2,
            rate_limiter=limiter,
            sleep=record_sleep,
        ) as client:
            with pytest.raises(SecClientError) as error:
                await client.get_json("https://data.sec.gov/example.json")

        assert error.value.attempts == 3
        assert sleeps == [2.0, 4.0]

    asyncio.run(scenario())
