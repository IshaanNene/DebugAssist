from __future__ import annotations

import pytest
from pydantic import SecretStr

from debugassist.core import openrouter
from debugassist.core.openrouter import ModelInfo
from debugassist.core.settings import Settings
from debugassist.llm import chat


@pytest.fixture
def catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    infos = {
        "openai/gpt-oss-120b": ModelInfo(
            id="openai/gpt-oss-120b",
            supported_parameters=["tools", "structured_outputs", "response_format"],
            price_in_per_mtok=0.04,
            price_out_per_mtok=0.2,
        ),
        "nvidia/nemotron-3-ultra-550b-a55b:free": ModelInfo(
            id="nvidia/nemotron-3-ultra-550b-a55b:free", supported_parameters=["tools", "tool_choice"]
        ),
    }

    def lookup(model: str) -> ModelInfo:
        return infos[model]

    monkeypatch.setattr(chat, "model_info", lookup)
    monkeypatch.setattr(openrouter, "model_info", lookup)


def _settings(model: str) -> Settings:
    return Settings(llm_model=model, open_router_api_key=SecretStr("test"), _env_file=None)  # pyright: ignore[reportCallIssue]


@pytest.mark.usefixtures("catalog")
def test_structured_output_method_follows_model_capabilities() -> None:
    assert chat.structured_method("openai/gpt-oss-120b") == "json_schema"
    assert chat.structured_method("nvidia/nemotron-3-ultra-550b-a55b:free") == "function_calling"


@pytest.mark.usefixtures("catalog")
def test_hosts_are_pinned_only_for_gpt_oss() -> None:
    s = _settings("nvidia/nemotron-3-ultra-550b-a55b:free")
    assert "order" not in chat.routing(s, s.llm_model)
    assert chat.routing(s, "openai/gpt-oss-120b")["order"] == ["groq", "cerebras", "crusoe", "deepinfra"]


@pytest.mark.usefixtures("catalog")
def test_cost_uses_published_prices() -> None:
    assert chat.cost_usd(1_000_000, 1_000_000, _settings("openai/gpt-oss-120b")) == pytest.approx(0.24)
    assert chat.cost_usd(5_000, 5_000, _settings("nvidia/nemotron-3-ultra-550b-a55b:free")) == 0.0
