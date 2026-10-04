"""Runtime settings and per-integration run modes.

Every external dependency runs in ``live`` or ``mock`` mode (LLM runs may also ``replay``
recorded transcripts). A mode is chosen per integration: an explicit ``DA_MODE_<NAME>`` wins;
otherwise the integration is live only when its credentials are present. CI sets no keys, so
everything resolves to mock.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Mode(StrEnum):
    LIVE = "live"
    MOCK = "mock"
    REPLAY = "replay"


class Integration(StrEnum):
    LLM = "llm"
    CLEF = "clef"
    GITHUB = "github"
    JIRA = "jira"
    SLACK = "slack"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM reasoning: OpenRouter, OpenAI-compatible API (PLAN.md amendment A1).
    open_router_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "openai/gpt-oss-120b"
    # gpt-oss structured output degenerates on some hosts under default routing; pin hosts that
    # passed our structured-output check (2026-10-04) and require them to honour every parameter.
    openrouter_provider_order: list[str] = ["groq", "cerebras", "crusoe", "deepinfra"]
    llm_price_in_per_mtok: float = 0.15
    llm_price_out_per_mtok: float = 0.75

    # Clef decision models on Cloudflare Workers AI.
    cloudflare_account_id: str | None = None
    cloudflare_api_key: SecretStr | None = None

    github_token: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("github_token", "github_api_key")
    )

    jira_api_key: SecretStr | None = None
    jira_base_url: str | None = None
    jira_email: str | None = None

    slack_bot_token: SecretStr | None = None

    # Dev default is SQLite; set postgresql+psycopg://debugassist:debugassist@localhost:5432/debugassist
    database_url: str = "sqlite+aiosqlite:///.data/debugassist.db"

    da_mode_llm: Mode | None = None
    da_mode_clef: Mode | None = None
    da_mode_github: Mode | None = None
    da_mode_jira: Mode | None = None
    da_mode_slack: Mode | None = None

    def _has_credentials(self, integration: Integration) -> bool:
        match integration:
            case Integration.LLM:
                return self.open_router_api_key is not None
            case Integration.CLEF:
                return self.cloudflare_account_id is not None and self.cloudflare_api_key is not None
            case Integration.GITHUB:
                return self.github_token is not None
            case Integration.JIRA:
                return None not in (self.jira_api_key, self.jira_base_url, self.jira_email)
            case Integration.SLACK:
                return self.slack_bot_token is not None

    def mode(self, integration: Integration) -> Mode:
        explicit: Mode | None = getattr(self, f"da_mode_{integration.value}")
        if explicit is not None:
            if explicit is Mode.LIVE and not self._has_credentials(integration):
                raise ValueError(f"DA_MODE_{integration.name}=live but its credentials are missing")
            if explicit is Mode.REPLAY and integration is not Integration.LLM:
                raise ValueError("replay mode is only supported for the LLM integration")
            return explicit
        return Mode.LIVE if self._has_credentials(integration) else Mode.MOCK

    def modes(self) -> dict[Integration, Mode]:
        return {i: self.mode(i) for i in Integration}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
