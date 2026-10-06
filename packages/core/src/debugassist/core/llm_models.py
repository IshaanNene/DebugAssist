"""Model capabilities and prices for the configured LLM provider, so the LLM layer adapts to the model.

OpenRouter publishes both per model (core.openrouter). GroqCloud's /models lists context windows only,
so capabilities come from its docs (checked 2026-10-04: tool use; strict structured outputs for
gpt-oss-120b/20b and qwen3.8-27b, not combinable with tools in one request; `reasoning_effort` for
gpt-oss). Groq prices are 0 for the free plan; on a paid plan set LLM_PRICE_IN/OUT_PER_MTOK.
"""

from __future__ import annotations

from debugassist.core.openrouter import ModelInfo
from debugassist.core.openrouter import model_info as openrouter_model_info
from debugassist.core.settings import LLMProvider, get_settings

_STRUCTURED = ["tools", "tool_choice", "structured_outputs", "response_format", "max_tokens"]
GROQ_MODELS: dict[str, ModelInfo] = {
    "openai/gpt-oss-120b": ModelInfo(
        id="openai/gpt-oss-120b",
        supported_parameters=[*_STRUCTURED, "reasoning_effort"],
        context_length=131_072,
    ),
    "openai/gpt-oss-20b": ModelInfo(
        id="openai/gpt-oss-20b",
        supported_parameters=[*_STRUCTURED, "reasoning_effort"],
        context_length=131_072,
    ),
    "qwen/qwen3.8-27b": ModelInfo(
        id="qwen/qwen3.8-27b", supported_parameters=_STRUCTURED, context_length=131_072
    ),
}


def model_info(model: str, provider: LLMProvider) -> ModelInfo:
    if provider == "groq":
        info = GROQ_MODELS.get(model) or ModelInfo(id=model, supported_parameters=["tools", "max_tokens"])
    else:
        info = openrouter_model_info(model)
    if get_settings().llm_structured_outputs is False:
        drop = {"structured_outputs", "response_format"}
        info = info.model_copy(
            update={"supported_parameters": [p for p in info.supported_parameters if p not in drop]}
        )
    return info
