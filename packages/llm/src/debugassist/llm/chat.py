"""Chat model factory for the configured OpenAI-compatible provider (GroqCloud or OpenRouter).

Endpoint, routing, structured-output method, reasoning effort and pricing follow the provider and the
model's capabilities (core.llm_models), so switching LLM_PROVIDER / LLM_MODEL needs no code change."""

from __future__ import annotations

from typing import Any, Literal

from langchain_openai import ChatOpenAI

from debugassist.core import ablation
from debugassist.core.llm_models import model_info
from debugassist.core.settings import Settings, get_settings


def routing(s: Settings, model: str) -> dict[str, object]:
    """OpenRouter's provider-routing preferences (unused on GroqCloud)."""
    out: dict[str, object] = {"require_parameters": True, "allow_fallbacks": True}
    if order := s.provider_order(model):
        out["order"] = order
    return out


def chat_model(
    effort: str = "medium", settings: Settings | None = None, model: str | None = None
) -> ChatOpenAI:
    s = settings or get_settings()
    key = s.llm_api_key()
    if key is None:
        raise RuntimeError(f"no API key for LLM provider {s.provider()!r} (use mock or replay mode)")
    name = model or s.model()
    kwargs: dict[str, Any] = {}
    if "reasoning_effort" in model_info(name, s.provider()).supported_parameters:
        cap = s.max_reasoning_effort()
        order = ["low", "medium", "high"]
        kwargs["reasoning_effort"] = cap if cap and order.index(effort) > order.index(cap) else effort
    if s.provider() == "openrouter":
        kwargs["extra_body"] = {"provider": routing(s, name)}
        # with_structured_output(function_calling) sends parallel_tool_calls=false; with require_parameters
        # no host of some models accepts it (404 "no endpoints"), so the extraction fallback never ran.
        kwargs["disabled_params"] = {"parallel_tool_calls": None}
    # Repeat runs per eval configuration. Not on OpenRouter: with require_parameters a `seed` restricts the
    # model to the hosts that accept one (for some models a single, often overloaded, host); hosted sampling
    # is not reproducible anyway, so eval seeds there are independent repeat samples.
    if (seed := ablation.llm_seed()) is not None and s.provider() != "openrouter":
        kwargs["seed"] = seed
    return ChatOpenAI(
        model=name,
        base_url=s.llm_base_url(),
        api_key=key,
        timeout=180,
        # OpenRouter reserves credit for it on every in-flight call; Groq counts part of it toward TPM.
        max_completion_tokens=s.max_output_tokens(),
        max_retries=3,
        **kwargs,
    )


def structured_method(model: str | None = None) -> Literal["json_schema", "function_calling"]:
    """Native json_schema where the model supports structured outputs, otherwise function calling."""
    s = get_settings()
    return (
        "json_schema"
        if model_info(model or s.model(), s.provider()).structured_outputs
        else "function_calling"
    )


def cost_usd(
    input_tokens: int, output_tokens: int, settings: Settings | None = None, model: str | None = None
) -> float:
    p_in, p_out = (settings or get_settings()).llm_prices(model)
    return (input_tokens * p_in + output_tokens * p_out) / 1_000_000
