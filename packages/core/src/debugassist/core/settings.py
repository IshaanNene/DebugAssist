"""Runtime settings and per-integration run modes.

Every external dependency runs in ``live`` or ``mock`` mode (LLM runs may also ``replay``
recorded transcripts). A mode is chosen per integration: an explicit ``DA_MODE_<NAME>`` wins;
otherwise the integration is live only when its credentials are present. CI sets no keys, so
everything resolves to mock.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProvider = Literal["groq", "openrouter"]
# Best free choice per provider (2026-10-04): gpt-oss-120b on GroqCloud's free plan (tools, strict
# structured outputs, reasoning effort); Nemotron 3 Ultra free on OpenRouter (no credits needed).
DEFAULT_MODELS: dict[LLMProvider, str] = {
    "groq": "openai/gpt-oss-120b",
    "openrouter": "nvidia/nemotron-3-ultra-550b-a55b:free",
}


GROQ_FREE_TPM = 8_000


class Mode(StrEnum):
    LIVE = "live"
    MOCK = "mock"
    REPLAY = "replay"


class Integration(StrEnum):
    LLM = "llm"
    CLEF = "clef"
    GITHUB = "github"
    JIRA = "jira"
    CHAT = "chat"  # team chat: a Discord channel webhook, or the local mock inbox


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM reasoning over OpenAI-compatible APIs: GroqCloud or OpenRouter (PLAN.md A1, A11, A12).
    # LLM_PROVIDER picks one explicitly; otherwise GroqCloud when its key is set, else OpenRouter.
    llm_provider: LLMProvider | None = None
    groq_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("groq_cloud_api", "groq_api_key")
    )
    groq_base_url: str = "https://api.groq.com/openai/v1"
    open_router_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Default model per provider (DEFAULT_MODELS) unless LLM_MODEL is set.
    llm_model: str | None = None
    # Groq's free plan allows 8K tokens per minute per model and counts part of max_completion_tokens
    # toward it (measured 2026-10-04), so on Groq the output cap is modest and the input budget is what
    # remains. LLM_MAX_REQUEST_TOKENS bounds prompt + tools + history (0 disables); see runner.
    llm_max_request_tokens: int | None = None
    llm_max_output_tokens: int | None = None
    # OpenRouter host pinning (see provider_order): gpt-oss structured output degenerates on some
    # hosts under default routing (2026-10-04). OPENROUTER_PROVIDER_ORDER overrides for every model.
    openrouter_provider_order: list[str] | None = None
    # Prices default to the provider's published pricing for the model (core.llm_models).
    llm_price_in_per_mtok: float | None = None
    llm_price_out_per_mtok: float | None = None

    def provider(self) -> LLMProvider:
        if self.llm_provider is not None:
            return self.llm_provider
        return "groq" if self.groq_api_key is not None else "openrouter"

    def model(self) -> str:
        return self.llm_model or DEFAULT_MODELS[self.provider()]

    def llm_base_url(self) -> str:
        return self.groq_base_url if self.provider() == "groq" else self.openrouter_base_url

    def llm_api_key(self) -> SecretStr | None:
        return self.groq_api_key if self.provider() == "groq" else self.open_router_api_key

    def max_output_tokens(self) -> int:
        if self.llm_max_output_tokens is not None:
            return self.llm_max_output_tokens
        return 2_500 if self.provider() == "groq" else 16_000

    def max_reasoning_effort(self) -> str | None:
        """Groq: long `high` reasoning would overrun the small output cap there."""
        return "medium" if self.provider() == "groq" else None

    def request_token_budget(self) -> int | None:
        if self.llm_max_request_tokens is not None:
            return self.llm_max_request_tokens or None
        return GROQ_FREE_TPM - self.max_output_tokens() - 500 if self.provider() == "groq" else None

    def provider_order(self, model: str | None = None) -> list[str]:
        """OpenRouter only: which upstream hosts to try, in order."""
        if self.openrouter_provider_order is not None:
            return self.openrouter_provider_order
        if (model or self.model()).startswith("openai/gpt-oss"):
            return ["groq", "cerebras", "crusoe", "deepinfra"]
        return []

    def llm_prices(self, model: str | None = None) -> tuple[float, float]:
        from debugassist.core.llm_models import model_info

        info = model_info(model or self.model(), self.provider())
        return (
            self.llm_price_in_per_mtok if self.llm_price_in_per_mtok is not None else info.price_in_per_mtok,
            self.llm_price_out_per_mtok
            if self.llm_price_out_per_mtok is not None
            else info.price_out_per_mtok,
        )

    # Clef decision models on Cloudflare Workers AI.
    cloudflare_account_id: str | None = None
    cloudflare_api_key: SecretStr | None = None

    github_token: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("github_token", "github_api_key")
    )

    jira_api_key: SecretStr | None = None
    jira_base_url: str | None = None
    jira_email: str | None = None

    discord_webhook_url: SecretStr | None = None  # the URL embeds its token: treat it as a secret

    # Dev default is SQLite; set postgresql+psycopg://debugassist:debugassist@localhost:5432/debugassist
    database_url: str = "sqlite+aiosqlite:///.data/debugassist.db"

    da_mode_llm: Mode | None = None
    da_mode_clef: Mode | None = None
    da_mode_github: Mode | None = None
    da_mode_jira: Mode | None = None
    da_mode_chat: Mode | None = None

    def _has_credentials(self, integration: Integration) -> bool:
        match integration:
            case Integration.LLM:
                return self.llm_api_key() is not None
            case Integration.CLEF:
                return self.cloudflare_account_id is not None and self.cloudflare_api_key is not None
            case Integration.GITHUB:
                return self.github_token is not None
            case Integration.JIRA:
                return None not in (self.jira_api_key, self.jira_base_url, self.jira_email)
            case Integration.CHAT:
                return self.discord_webhook_url is not None

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
