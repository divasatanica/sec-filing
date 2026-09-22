"""Typed application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the local service.

    Keep secrets and deployment-specific values in `.env`, never in source code.
    Environment variables use the `SEC_FILING_AGENT_` prefix.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SEC_FILING_AGENT_",
        extra="ignore",
    )

    app_name: str = "SEC Filing Agent"
    environment: str = "development"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    data_dir: Path = Path("data")
    sec_user_agent: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Return one settings object per process."""

    return Settings()
