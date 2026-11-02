"""Application settings, loaded once from the environment (and `.env` in development).

Everything that differs between laptop, CI and production lives here so the rest of
the code base never reads `os.environ` directly.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Comma-separated in the environment; NoDecode stops pydantic-settings parsing them as JSON.
CSVList = Annotated[list[str], NoDecode]

Environment = Literal["development", "test", "production"]
LLMProviderName = Literal["anthropic", "openai"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # App
    app_env: Environment = "development"
    log_level: str = "INFO"
    secret_key: SecretStr = SecretStr("dev-only-secret-change-me")
    cors_origins: CSVList = Field(default_factory=lambda: ["http://localhost:3000"])
    public_web_url: str = "http://localhost:3000"
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    rate_limit_default: str = "120/minute"
    rate_limit_auth: str = "10/minute"
    upload_dir: str = "uploads"

    # Data stores
    database_url: PostgresDsn = Field(
        default=PostgresDsn("postgresql+asyncpg://jobhunt:jobhunt@localhost:5432/jobhunt")
    )
    redis_url: RedisDsn = Field(default=RedisDsn("redis://localhost:6379/0"))

    # LLM providers and model routing
    llm_provider: LLMProviderName = "anthropic"
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    model_extract: str = "claude-haiku-5-5"
    model_judge: str = "claude-opus-5-5"
    model_write: str = "claude-opus-5-5"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Observability
    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # Email
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str = "jobhunt@example.com"
    smtp_use_tls: bool = True

    # Job sources
    greenhouse_boards: CSVList = Field(default_factory=list)
    lever_boards: CSVList = Field(default_factory=list)

    @field_validator("cors_origins", "greenhouse_boards", "lever_boards", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Accept comma-separated strings from the environment as well as JSON lists."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    @property
    def sync_database_url(self) -> str:
        """Driver-less URL for Alembic and other synchronous tooling."""
        return str(self.database_url).replace("+asyncpg", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
