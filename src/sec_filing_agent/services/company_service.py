"""Company entity relevant service"""

from sqlalchemy import select

from sec_filing_agent.db.session import SessionLocal
from sec_filing_agent.db.tables import CompanyTicker


class CIKNotFoundError(LookupError):
    """CIK should exist in with specific ticker"""


class CompanyService:
    async def get_cik_by_ticker(self, ticker: str) -> str:
        async with SessionLocal() as session:
            result = await session.scalar(
                select(CompanyTicker).where(CompanyTicker.ticker == ticker)
            )

            if result is None:
                raise CIKNotFoundError(str(ticker))

        return result.cik

    async def get_cik_map(self, tickers: list[str]) -> dict[str, str]:
        result = {}

        async with SessionLocal() as session:
            rows = await session.scalars(
                select(CompanyTicker).where(CompanyTicker.ticker.in_(tickers))
            )

            if rows is None:
                raise CIKNotFoundError(str(tickers))

            for row in rows:
                result[row.ticker] = row.cik

        return result
