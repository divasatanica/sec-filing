"""SEC Edgar API Client"""

import asyncio

import httpx
import structlog

from sec_filing_agent.core.config import get_settings

settings = get_settings()
logger = structlog.get_logger(__name__)

SEC_BASE_DOMAIN = "https://www.sec.gov"
SEC_DATA_DOMAIN = "https://data.sec.gov"
SEC_USER_AGENT = settings.sec_user_agent or ""
MAX_RETRIES = 3
RETRY_BASE_DELAY_SECOND = 0.5


class CompanyTickerEntry:
    cik_str: int
    ticker: str
    title: str


def cik_to_10digits(cik: int | str):
    if not isinstance(cik, int) and not isinstance(cik, str):
        raise ValueError("CIK must be a number or string with digits char only")

    if isinstance(cik, int):
        result = str(cik)
    else:
        result = cik

    return f"{'0' * (10 - len(result))}{result}"


async def fetch_api(url: str):
    attempt = 0

    async with httpx.AsyncClient() as client:
        retries = MAX_RETRIES
        while attempt <= retries:
            try:
                response = await client.get(
                    url=url, headers={"User-Agent": SEC_USER_AGENT, "Accept": "application/json"}
                )
                response.raise_for_status()

                return response
            except httpx.HTTPStatusError as error:
                error_status_code = error.response.status_code
                if (error_status_code == 429 or error_status_code == 503) and attempt < retries:
                    retry_after = error.response.headers.get("Retry-After")
                    delay_seconds = (
                        int(retry_after)
                        if retry_after is not None
                        else pow(RETRY_BASE_DELAY_SECOND, 2 * attempt)
                    )
                    logger.warning(
                        f"{error_status_code} for {url}, \
                            retrying ({attempt + 1}/{retries}) in {delay_seconds} seconds"
                    )
                    await asyncio.sleep(delay_seconds)
                    continue
                else:
                    raise
            finally:
                attempt += 1

        raise RuntimeError(
            f"Retry loop ended after {attempt} attempts without a response, url: {url}"
        )


ticker_map: dict[str, CompanyTickerEntry] | None = None


def get_current_cache_ticker_map() -> dict[str, CompanyTickerEntry] | None:
    return ticker_map


async def get_ticker_map() -> dict[str, CompanyTickerEntry]:
    global ticker_map
    if ticker_map is not None:
        return ticker_map

    logger.info("Fetching company_tickers.json...")
    response = await fetch_api(f"{SEC_BASE_DOMAIN}/files/company_tickers.json")
    data = response.json()

    ticker_map = {}
    for key in data:
        ticker_object = data[key]
        ticker_map[ticker_object["ticker"]] = ticker_object

    logger.info(f"Loaded {len(ticker_map)} ticker->CIK mappings")
    return ticker_map


async def get_submissions(cik10: str):
    response = await fetch_api(f"{SEC_DATA_DOMAIN}/submissions/CIK{cik10}.json")

    return response
