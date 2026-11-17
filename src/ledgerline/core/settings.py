"""Application settings loaded from environment / .env via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ModelProfileName = Literal["cheap", "quality"]
ProviderName = Literal["auto", "anthropic", "openrouter"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LEDGERLINE_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Anthropic. Read without the prefix so the SDK convention keeps working.
    anthropic_api_key: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    openrouter_api_key: SecretStr | None = Field(
        default=None, validation_alias="OPENROUTER_API_KEY"
    )
    # auto: Anthropic direct if ANTHROPIC_API_KEY is set, else OpenRouter if its key is set.
    llm_provider: ProviderName = "auto"
    openrouter_base_url: str = "https://openrouter.ai/api"
    model_profile: ModelProfileName = "cheap"

    # Spend guards (USD). Enforced in core.budget before and after every LLM call.
    max_usd_per_run: float = 1.00
    max_usd_per_day: float = 5.00

    # Paths
    data_dir: Path = Path("data")
    dataroom_dir: Path = Path("dataroom")
    corpus_dir: Path = Path("corpus/regulatory")
    audit_log_path: Path = Path("data/audit/audit.jsonl")
    llm_cache_path: Path = Path("data/cache/llm_cache.sqlite")
    llm_cache_enabled: bool = True

    # Observability: none | file | otlp (e.g. self-hosted Langfuse)
    otel_exporter: Literal["none", "file", "otlp"] = "none"
    otel_endpoint: str | None = None

    # Services
    qdrant_url: str = "http://localhost:6333"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("ledgerline-dev")
    postgres_dsn: str = "postgresql+psycopg://ledgerline:ledgerline@localhost:55432/ledgerline"

    @field_validator("anthropic_api_key", "openrouter_api_key", mode="before")
    @classmethod
    def _blank_is_none(cls, v: object) -> object:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return v

    def resolved_provider(self) -> Literal["anthropic", "openrouter"] | None:
        if self.llm_provider != "auto":
            return self.llm_provider
        if self.anthropic_api_key is not None:
            return "anthropic"
        if self.openrouter_api_key is not None:
            return "openrouter"
        return None

    def llm_configured(self) -> bool:
        return self.resolved_provider() is not None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
