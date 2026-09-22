"""Typed application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the local service.

    Keep secrets and deployment-specific values in `.env`, never in source code.
    Environment variables use the `APP_` prefix.
    """

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        env_prefix="SEC_FILING_AGENT_",
        extra="ignore",
    )

    sec_user_agent: str
    app_name: str = "FastAPI Service"
    environment: str = "development"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: str = "INFO"
    log_json: bool | None = None

    def __init__(self, environment: str = "development", **values: Any) -> None:
        """Load settings from the file associated with ``environment``."""

        super().__init__(
            _env_file=f".env.{environment}",
            environment=environment,
            **values,
        )

    @property
    def use_json_logs(self) -> bool:
        """Choose JSON logs outside local development unless explicitly overridden."""

        return self.log_json if self.log_json is not None else self.environment != "development"


@lru_cache
def get_settings(environment: str = "development") -> Settings:
    """Return one settings object per process."""

    return Settings(environment=environment)
