"""LLM baseline decider: the same questions answered by the configured LLM with verbalised probabilities.

Uses Typesafe's ``system-one-adapter`` with an OpenAI-compatible provider pointed at GroqCloud or
OpenRouter. This is ablation (1) "no Clef" and the circuit-breaker fallback. The default models are
text-only, so images are dropped (and the drop is reported via ``last_note``).
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, cast, override

from system_one_adapter import AsyncSystemOneAdapterClient
from system_one_adapter.providers.base import (
    Message,
    ProviderResult,
    record_request,
    record_response,
    render_messages,
    translating,
)
from system_one_adapter.providers.openai import (  # pyright: ignore[reportPrivateUsage]
    AsyncOpenAIProvider,
)
from typesafe_sdk import TypeSafeError

from debugassist.core.llm_models import model_info
from debugassist.core.settings import LLMProvider, Mode, Settings
from debugassist.decisions.schema import ClefRequest, ClefResponse, ClefTransientError, Usage


def extra_body(
    provider: LLMProvider, provider_order: list[str], reasoning_effort: str | None
) -> dict[str, Any]:
    """Provider-specific request fields.

    OpenRouter: default routing sometimes lands on hosts whose gpt-oss structured output degenerates
    into whitespace; requiring every parameter and pinning tested hosts avoids that (PLAN.md A1).
    GroqCloud takes `reasoning_effort` as a top-level field.
    """
    if provider == "groq":
        return {"reasoning_effort": reasoning_effort} if reasoning_effort else {}
    body: dict[str, Any] = {
        "provider": {"require_parameters": True, "allow_fallbacks": True}
        | ({"order": provider_order} if provider_order else {})
    }
    if reasoning_effort:
        body["reasoning"] = {"effort": reasoning_effort}
    return body


class CompatProvider(AsyncOpenAIProvider):
    """Chat Completions on an OpenAI-compatible endpoint with provider fields and a token cap."""

    def __init__(
        self, model_name: str, *, base_url: str, api_key: str, body: dict[str, Any], max_tokens: int = 2000
    ) -> None:
        super().__init__(model_name, base_url=base_url, api_key=api_key, api="chat_completions")
        self._extra_body = body
        self._max_tokens = max_tokens

    @override
    async def request(
        self, messages: list[Message], *, schema: dict[str, Any], structured: bool
    ) -> ProviderResult:
        with translating(self.translate_error):
            kwargs: dict[str, Any] = {
                "model": self.model_name,
                "messages": render_messages(messages),
                "max_tokens": self._max_tokens,
                "extra_body": self._extra_body,
            }
            if structured:
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "evaluation", "schema": schema, "strict": True},
                }
            record_request(kwargs, api=self.api)
            response = cast(Any, await self._client.chat.completions.create(**kwargs))
        finish = response.choices[0].finish_reason
        record_response(response, finish_reason=finish)
        if finish not in ("stop", None):
            raise TypeSafeError(f"chat completion did not complete: {finish}")
        return ProviderResult(
            text=response.choices[0].message.content or "",
            input_tokens=getattr(response.usage, "prompt_tokens", None),
            output_tokens=getattr(response.usage, "completion_tokens", None),
        )


RATE_LIMIT_BACKOFF_S = (5.0, 15.0, 30.0)
_RETRYABLE = re.compile(r"\b(429|5\d\d)\b|rate.?limit|timed? ?out|overloaded", re.I)


class LLMDecider:
    name = "llm"
    mode = Mode.LIVE

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        provider_order: list[str],
        price_in_per_mtok: float,
        price_out_per_mtok: float,
        reasoning_effort: str | None = "low",
        structured_outputs: bool = True,
        provider_name: LLMProvider = "openrouter",
    ) -> None:
        self.model = model
        self._price_in = price_in_per_mtok
        self._price_out = price_out_per_mtok
        provider = CompatProvider(
            model,
            base_url=base_url,
            api_key=api_key,
            body=extra_body(provider_name, provider_order, reasoning_effort),
        )
        self._provider = provider
        self._client = AsyncSystemOneAdapterClient(
            structured_outputs=structured_outputs,  # prompted JSON when the model has no response_format
            llm_answer_mode="probabilities",
            normalize_probabilities=True,
            n_retry_malformed_structure=2,
            model=provider,
        )
        self.last_note: str | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> LLMDecider:
        key = settings.llm_api_key()
        if key is None:
            raise ValueError(
                f"an API key for LLM provider {settings.provider()!r} is required for the LLM decider"
            )
        prices = settings.llm_prices()
        info = model_info(settings.model(), settings.provider())
        return cls(
            model=settings.model(),
            base_url=settings.llm_base_url(),
            api_key=key.get_secret_value(),
            provider_order=settings.provider_order(),
            price_in_per_mtok=prices[0],
            price_out_per_mtok=prices[1],
            reasoning_effort="low" if "reasoning_effort" in info.supported_parameters else None,
            structured_outputs=info.structured_outputs,
            provider_name=settings.provider(),
        )

    async def run(self, request: ClefRequest) -> ClefResponse:
        self.last_note = (
            f"dropped {len(request.images)} image(s): text-only model" if request.images else None
        )
        body = request.body()
        for delay in (*RATE_LIMIT_BACKOFF_S, None):
            try:
                result = await self._client.system_one(body["state"], body["questions"])
                break
            except TypeSafeError as exc:
                # Provider rate limits and upstream hiccups clear in seconds, longer than the engine's retries.
                if delay is None or not _RETRYABLE.search(str(exc)):
                    raise ClefTransientError(f"LLM decider failed: {exc}") from exc
                await asyncio.sleep(delay)
        else:  # pragma: no cover - the loop always breaks or raises
            raise AssertionError("unreachable")
        dumped = result.model_dump(mode="json")
        usage = result.usage
        parsed = ClefResponse.model_validate(
            {
                "model": self.model,
                "answers": dumped["answers"],
                "usage": Usage(
                    input_tokens=usage.input_tokens_total or usage.input_tokens or 0,
                    output_tokens=usage.output_tokens_total or usage.output_tokens or 0,
                ),
            }
        )
        parsed.check_against(request)
        return parsed

    def cost_usd(self, response: ClefResponse) -> float:
        u = response.usage
        return (u.input_tokens * self._price_in + u.output_tokens * self._price_out) / 1_000_000

    async def aclose(self) -> None:
        await self._provider.aclose()
