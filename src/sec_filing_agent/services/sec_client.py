"""Asynchronous, rate-limited client for the SEC EDGAR public endpoints."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import monotonic
from typing import Any, TypeVar
from urllib.parse import urlparse

import httpx
import structlog

from sec_filing_agent.core.config import get_settings

settings = get_settings()

SEC_BASE_DOMAIN = "https://www.sec.gov"
SEC_DATA_DOMAIN = "https://data.sec.gov"
MAX_RETRIES = 3
# Preserve the requested 2 / 4 / 8 second retry sequence.
RETRY_BASE_DELAY_SECONDS = 2.0

JSON_ACCEPT = "application/json"
HTML_ACCEPT = "text/html,application/xhtml+xml"
DEFAULT_TIMEOUT = httpx.Timeout(timeout=30.0, connect=10.0)
DEFAULT_RATE_LIMITS = {
    "data.sec.gov": 0.2,
    "www.sec.gov": 0.6,
}

logger = structlog.get_logger(__name__)
T = TypeVar("T")


class SecClientError(RuntimeError):
    """A failed SEC request with safe, machine-readable context."""

    def __init__(
        self,
        message: str,
        *,
        url: str,
        status_code: int | None = None,
        attempts: int = 1,
    ) -> None:
        super().__init__(message)
        self.url = url
        self.status_code = status_code
        self.attempts = attempts


class DomainRateLimiter:
    """Serialize requests per host so concurrent collectors honour SEC pacing."""

    def __init__(
        self,
        intervals: dict[str, float] | None = None,
        *,
        clock: Callable[[], float] = monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._intervals = {**DEFAULT_RATE_LIMITS, **(intervals or {})}
        self._clock = clock
        self._sleep = sleep
        # The lock guards the read-wait-write sequence for one hostname. Without it,
        # concurrent coroutines could all observe the same last-request timestamp.
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._last_request_at: dict[str, float] = {}

    async def wait(self, url: str) -> None:
        host = urlparse(url).hostname or ""
        interval = self._intervals.get(host, 0.4)
        async with self._locks[host]:
            previous = self._last_request_at.get(host)
            if previous is not None:
                remaining = interval - (self._clock() - previous)
                if remaining > 0:
                    await self._sleep(remaining)
            self._last_request_at[host] = self._clock()


class SecClient:
    """Endpoint-specific SEC client suitable for dependency injection and mocks."""

    def __init__(
        self,
        user_agent: str = settings.sec_user_agent,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
        rate_limiter: DomainRateLimiter | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not user_agent.strip():
            raise ValueError("SEC user_agent must identify the application and a contact address")
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=timeout,
            transport=transport,
        )
        self._max_retries = max_retries
        self._rate_limiter = rate_limiter or DomainRateLimiter()
        self._sleep = sleep

    async def __aenter__(self) -> SecClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_json(self, url: str) -> dict[str, Any]:
        data = await self._request(
            url,
            accept=JSON_ACCEPT,
            decoder=lambda response: response.json(),
        )
        if not isinstance(data, dict):
            raise SecClientError(
                "SEC JSON response must be an object", url=url, attempts=self._max_retries + 1
            )
        return data

    async def get_text(self, url: str, *, accept: str = HTML_ACCEPT) -> str:
        text = await self._request(url, accept=accept, decoder=lambda response: response.text)
        if not isinstance(text, str):  # Defensive: makes the public contract explicit.
            raise SecClientError("SEC text response was not text", url=url)
        return text

    async def get_response(self, url: str, *, accept: str = JSON_ACCEPT) -> httpx.Response:
        response = await self._request(url, accept=accept)
        if not isinstance(response, httpx.Response):  # pragma: no cover - type narrowing guard
            raise SecClientError("SEC response had an unexpected type", url=url)
        return response

    async def get_ticker_map(self) -> dict[str, dict[str, Any]]:
        global ticker_map
        if ticker_map is not None:
            return ticker_map

        # Keep the process cache, but only allow one cold-start download.
        async with _ticker_map_lock:
            if ticker_map is not None:
                return ticker_map
            data = await self.get_json(f"{SEC_BASE_DOMAIN}/files/company_tickers.json")
            loaded: dict[str, dict[str, Any]] = {}
            for entry in data.values():
                if not isinstance(entry, dict):
                    continue
                ticker = entry.get("ticker")
                if isinstance(ticker, str):
                    loaded[ticker.upper()] = entry
            ticker_map = loaded
            logger.info("ticker_map_loaded", ticker_count=len(loaded))
            return loaded

    async def get_submissions(self, cik10: str) -> dict[str, Any]:
        url = f"{SEC_DATA_DOMAIN}/submissions/CIK{cik_to_10digits(cik10)}.json"
        return await self.get_json(url)

    async def get_historical_submissions(self, filename: str) -> dict[str, Any]:
        if not filename or "/" in filename or ".." in filename:
            raise ValueError("historical submissions filename is invalid")
        return await self.get_json(f"{SEC_DATA_DOMAIN}/submissions/{filename}")

    async def get_archive_index(self, archive_directory_url: str) -> dict[str, Any]:
        return await self.get_json(f"{archive_directory_url.rstrip('/')}/index.json")

    async def get_company_facts(self, cik10: str) -> dict[str, Any]:
        return await self.get_json(
            f"{SEC_DATA_DOMAIN}/api/xbrl/companyfacts/CIK{cik_to_10digits(cik10)}.json"
        )

    async def _request(
        self,
        url: str,
        *,
        accept: str,
        decoder: Callable[[httpx.Response], T] | None = None,
    ) -> httpx.Response | T:
        for attempt in range(self._max_retries + 1):
            # Retries are real SEC requests too, so each one goes through the limiter.
            await self._rate_limiter.wait(url)
            started_at = monotonic()
            try:
                response = await self._client.get(url, headers={"Accept": accept})
            except httpx.RequestError as error:
                if attempt < self._max_retries:
                    await self._wait_before_retry(url, attempt, None, type(error).__name__)
                    continue
                raise SecClientError(
                    f"SEC request failed: {type(error).__name__}",
                    url=url,
                    attempts=attempt + 1,
                ) from error

            duration_ms = round((monotonic() - started_at) * 1_000, 2)
            if response.status_code in {429, 503} and attempt < self._max_retries:
                await self._wait_before_retry(url, attempt, response, str(response.status_code))
                continue
            if response.is_error:
                preview = response.text[:300].replace("\n", " ")
                logger.warning(
                    "sec_request_failed",
                    url=url,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    response_preview=preview,
                )
                raise SecClientError(
                    f"SEC responded with HTTP {response.status_code}",
                    url=url,
                    status_code=response.status_code,
                    attempts=attempt + 1,
                )

            try:
                # A 200 HTML error page from an upstream proxy is still a decode failure
                # for JSON endpoints, and should get the same bounded retry treatment.
                result = decoder(response) if decoder else response
            except (TypeError, ValueError) as error:
                if attempt < self._max_retries:
                    await self._wait_before_retry(url, attempt, response, "decode_error")
                    continue
                raise SecClientError(
                    "SEC response could not be decoded", url=url, attempts=attempt + 1
                ) from error

            logger.info(
                "sec_request_completed",
                url=url,
                status_code=response.status_code,
                duration_ms=duration_ms,
                attempt=attempt + 1,
            )
            return result

        raise AssertionError("retry loop must either return or raise")  # pragma: no cover

    async def _wait_before_retry(
        self,
        url: str,
        attempt: int,
        response: httpx.Response | None,
        reason: str,
    ) -> None:
        retry_after = response.headers.get("Retry-After") if response else None
        parsed_retry_after = _parse_retry_after(retry_after)
        delay_seconds = (
            parsed_retry_after
            if parsed_retry_after is not None
            else RETRY_BASE_DELAY_SECONDS * (2**attempt)
        )
        logger.warning(
            "sec_request_retrying",
            url=url,
            reason=reason,
            retry_attempt=attempt + 1,
            delay_seconds=delay_seconds,
        )
        await self._sleep(delay_seconds)


def cik_to_10digits(cik: int | str) -> str:
    """Return a valid SEC CIK padded to the ten digits used by data.sec.gov."""

    value = str(cik).strip()
    if not value.isdigit() or len(value) > 10:
        raise ValueError("CIK must contain one to ten digits")
    return value.zfill(10)


def cik_to_archive_path(cik: int | str) -> str:
    """Return the unpadded CIK representation required by EDGAR Archives URLs."""

    return str(int(cik_to_10digits(cik)))


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())


# Compatibility helpers used by the existing FastAPI scaffold. New code should inject SecClient.
ticker_map: dict[str, dict[str, Any]] | None = None
_ticker_map_lock = asyncio.Lock()


def get_current_cache_ticker_map() -> dict[str, dict[str, Any]] | None:
    return ticker_map


async def _configured_client() -> SecClient:
    from sec_filing_agent.core.config import get_settings

    return SecClient(get_settings().sec_user_agent)


async def fetch_api(url: str) -> httpx.Response:
    async with await _configured_client() as client:
        return await client.get_response(url)


async def get_ticker_map() -> dict[str, dict[str, Any]]:
    async with await _configured_client() as client:
        return await client.get_ticker_map()


async def get_submissions(cik10: str) -> httpx.Response:
    async with await _configured_client() as client:
        return await client.get_response(
            f"{SEC_DATA_DOMAIN}/submissions/CIK{cik_to_10digits(cik10)}.json"
        )
