from __future__ import annotations

import pytest
from pydantic import SecretStr

from debugassist.core import llm_models
from debugassist.core.openrouter import ModelInfo
from debugassist.core.settings import LLMProvider, Settings
from debugassist.decisions.backends.llm import extra_body
from debugassist.llm import chat

NEMOTRON = "nvidia/nemotron-3-ultra-550b-a55b:free"


@pytest.fixture(autouse=True)
def openrouter_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    infos = {
        "openai/gpt-oss-120b": ModelInfo(
            id="openai/gpt-oss-120b",
            supported_parameters=["tools", "structured_outputs", "response_format", "reasoning_effort"],
            price_in_per_mtok=0.04,
            price_out_per_mtok=0.2,
        ),
        NEMOTRON: ModelInfo(id=NEMOTRON, supported_parameters=["tools", "tool_choice", "reasoning_effort"]),
    }

    def lookup(model: str) -> ModelInfo:
        return infos[model]

    monkeypatch.setattr(llm_models, "openrouter_model_info", lookup)


def _settings(provider: LLMProvider | None = None, model: str | None = None, **kw: object) -> Settings:
    keys = {"groq_api_key": SecretStr("g"), "open_router_api_key": SecretStr("o")}
    return Settings(llm_provider=provider, llm_model=model, _env_file=None, **{**keys, **kw})  # pyright: ignore[reportCallIssue,reportArgumentType]


def test_provider_resolution_and_defaults() -> None:
    assert _settings().provider() == "groq"  # GroqCloud wins when its key is present
    assert Settings(open_router_api_key=SecretStr("o"), _env_file=None).provider() == "openrouter"  # pyright: ignore[reportCallIssue]
    groq, orr = _settings("groq"), _settings("openrouter")
    assert groq.model() == "openai/gpt-oss-120b" and groq.llm_base_url().startswith("https://api.groq.com/")
    assert orr.model() == NEMOTRON and orr.llm_base_url().startswith("https://openrouter.ai/")
    assert groq.max_output_tokens() == 2_500 and orr.max_output_tokens() == 16_000
    assert groq.request_token_budget() == 5_000 and orr.request_token_budget() is None
    assert _settings("groq", llm_max_request_tokens=0).request_token_budget() is None


def test_chat_model_sends_provider_specific_fields() -> None:
    groq = chat.chat_model("high", _settings("groq"))
    assert groq.reasoning_effort == "medium" and not groq.extra_body  # capped on Groq
    orr = chat.chat_model("low", _settings("openrouter", "openai/gpt-oss-120b"))
    assert orr.extra_body and orr.extra_body["provider"]["order"] == [
        "groq",
        "cerebras",
        "crusoe",
        "deepinfra",
    ]
    qwen = chat.chat_model("high", _settings("groq", "qwen/qwen3.8-27b"))
    assert qwen.reasoning_effort is None  # not a reasoning-effort model


def test_structured_output_method_and_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat, "get_settings", lambda: _settings("openrouter"))
    assert chat.structured_method("openai/gpt-oss-120b") == "json_schema"
    assert chat.structured_method(NEMOTRON) == "function_calling"
    assert chat.cost_usd(
        1_000_000, 1_000_000, _settings("openrouter", "openai/gpt-oss-120b")
    ) == pytest.approx(0.24)
    assert chat.cost_usd(1_000_000, 1_000_000, _settings("groq")) == 0.0  # Groq free plan


def test_decider_request_fields() -> None:
    assert extra_body("groq", [], "low") == {"reasoning_effort": "low"}
    assert extra_body("groq", [], None) == {}
    body = extra_body("openrouter", ["groq"], "low")
    assert body["provider"]["order"] == ["groq"] and body["reasoning"] == {"effort": "low"}
