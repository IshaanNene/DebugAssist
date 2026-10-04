"""Chat model factory for OpenRouter. Routing, structured-output method and pricing follow the model's
published capabilities (core.openrouter), so switching `LLM_MODEL` needs no code change."""

from __future__ import annotations

from typing import Literal

from langchain_openai import ChatOpenAI

from debugassist.core.openrouter import model_info
from debugassist.core.settings import Settings, get_settings


def routing(s: Settings, model: str) -> dict[str, object]:
    out: dict[str, object] = {"require_parameters": True, "allow_fallbacks": True}
    if order := s.provider_order(model):
        out["order"] = order
    return out


def chat_model(
    effort: str = "medium", settings: Settings | None = None, model: str | None = None
) -> ChatOpenAI:
    s = settings or get_settings()
    if s.open_router_api_key is None:
        raise RuntimeError("OPEN_ROUTER_API_KEY is not set (use mock or replay mode)")
    name = model or s.llm_model
    return ChatOpenAI(
        model=name,
        base_url=s.openrouter_base_url,
        api_key=s.open_router_api_key,
        reasoning_effort=effort,
        timeout=180,
        max_completion_tokens=16_000,  # OpenRouter reserves credit for max_tokens on every in-flight call
        max_retries=3,
        extra_body={"provider": routing(s, name)},
    )


def structured_method(model: str | None = None) -> Literal["json_schema", "function_calling"]:
    """Native json_schema where the model supports structured outputs, otherwise function calling."""
    name = model or get_settings().llm_model
    return "json_schema" if model_info(name).structured_outputs else "function_calling"


def cost_usd(
    input_tokens: int, output_tokens: int, settings: Settings | None = None, model: str | None = None
) -> float:
    p_in, p_out = (settings or get_settings()).llm_prices(model)
    return (input_tokens * p_in + output_tokens * p_out) / 1_000_000
