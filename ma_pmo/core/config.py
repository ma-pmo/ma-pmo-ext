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

    # API authentication (see docs/AUTH.md): off | api_key | custom
    auth_mode: str = Field(default="off", alias="MA_PMO_AUTH_MODE")
    # api_key mode: "name:role+role:key,..." — roles: viewer, operator, approver, admin
    api_keys: str = Field(default="", alias="MA_PMO_API_KEYS")
    # custom mode: "package.module:factory" returning an object with authenticate(request)
    authenticator: str = Field(default="", alias="MA_PMO_AUTHENTICATOR")

    # observability
    otel_enabled: bool = Field(default=False, alias="OTEL_ENABLED")

    # default language for generated text and LLM output: en | ko
    default_lang: str = Field(default="en", alias="MA_PMO_LANG")

    # integrations (see docs/INTEGRATIONS.md): comma-separated names, e.g. "slack,jira"
    integrations: str = Field(default="", alias="MA_PMO_INTEGRATIONS")
    # which event types notifiers receive (comma-separated); empty = all
    notify_events: str = Field(default="", alias="MA_PMO_NOTIFY_EVENTS")
    integration_timeout_sec: float = Field(default=5.0, alias="MA_PMO_INTEGRATION_TIMEOUT")
    # base URL of the dashboard, used for links in notifications
    public_url: str = Field(default="http://localhost:3000", alias="MA_PMO_PUBLIC_URL")

    slack_webhook_url: str = Field(default="", alias="SLACK_WEBHOOK_URL")
    webhook_url: str = Field(default="", alias="MA_PMO_WEBHOOK_URL")

    jira_base_url: str = Field(default="", alias="JIRA_BASE_URL")
    jira_email: str = Field(default="", alias="JIRA_EMAIL")
    jira_api_token: str = Field(default="", alias="JIRA_API_TOKEN")
    # Jira project keys that form the portfolio, e.g. "PAY,DATA"
    jira_project_keys: str = Field(default="", alias="JIRA_PROJECT_KEYS")
    # custom field holding story points (used as effort when there is no time estimate)
    jira_story_points_field: str = Field(default="", alias="JIRA_STORY_POINTS_FIELD")


@lru_cache
def get_settings() -> Settings:
    return Settings()
