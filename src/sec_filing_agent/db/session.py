"""Async SQLAlchemy session primitives shared by database-facing services."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sec_filing_agent.core.config import get_settings


def create_engine(database_url: str) -> AsyncEngine:
    """Create an engine with a health check before reusing pooled connections."""

    return create_async_engine(database_url, pool_pre_ping=True)


# Services use this factory to create a short-lived session for one unit of work.
# Do not share an AsyncSession across concurrent tasks.
engine = create_engine(get_settings().database_url)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def close_database() -> None:
    """Release pooled PostgreSQL connections during application shutdown or tests."""

    await engine.dispose()
