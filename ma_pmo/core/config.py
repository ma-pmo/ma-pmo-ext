"""Global settings — loaded from .env via pydantic-settings.

Paper §5 tech stack: the LLM gateway abstracts providers (LiteLLM); state is
lightweight first (SQLite).
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # LLM gateway (provider abstraction — Anthropic/Ollama/others)
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    llm_model: str = Field(default="anthropic/claude-sonnet-5", alias="LLM_MODEL")
    llm_model_fast: str = Field(
        default="anthropic/claude-haiku-4-5-20251001", alias="LLM_MODEL_FAST"
    )
    # local/private endpoint (e.g. Ollama http://localhost:11434); empty = provider default
    llm_api_base: str = Field(default="", alias="LLM_API_BASE")
    llm_temperature: float = Field(default=0.2, alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=4096, alias="LLM_MAX_TOKENS")

    # data / state
    db_url: str = Field(default="sqlite:///./ma_pmo.db", alias="DB_URL")
    checkpoint_db: str = Field(
        default="./ma_pmo_checkpoints.sqlite", alias="CHECKPOINT_DB"
    )

    # HITL / governance
    hitl_confidence_threshold: float = Field(
        default=0.6, alias="HITL_CONFIDENCE_THRESHOLD"
    )

    # API
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")

    # observability
    otel_enabled: bool = Field(default=False, alias="OTEL_ENABLED")

    # default language for generated text and LLM output: en | ko
    default_lang: str = Field(default="en", alias="MA_PMO_LANG")


@lru_cache
def get_settings() -> Settings:
    return Settings()
