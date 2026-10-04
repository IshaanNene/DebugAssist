"""LLM baseline decider: the same questions answered by gpt-oss-120b with verbalised probabilities.

Uses Typesafe's ``system-one-adapter`` (OpenAI-compatible provider pointed at OpenRouter). This is
ablation (1) "no Clef" and the circuit-breaker fallback. gpt-oss-120b is text-only, so images are
dropped (and the drop is reported via ``last_note``).
"""

from __future__ import annotations

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

from debugassist.core.settings import Mode, Settings
from debugassist.decisions.schema import ClefRequest, ClefResponse, ClefTransientError, Usage


class OpenRouterProvider(AsyncOpenAIProvider):
    """Chat Completions on OpenRouter with pinned hosts, low reasoning effort and a token cap.

    Default routing sometimes lands on hosts whose gpt-oss structured output degenerates into
    whitespace; requiring every parameter and pinning tested hosts avoids that (PLAN.md A1).
    """

    def __init__(
        self,
        model_name: str,
        *,
        base_url: str,
        api_key: str,
        provider_order: list[str],
        reasoning_effort: str = "low",
        max_tokens: int = 2000,
    ) -> None:
        super().__init__(model_name, base_url=base_url, api_key=api_key, api="chat_completions")
        self._extra_body: dict[str, Any] = {
            "provider": {"order": provider_order, "require_parameters": True, "allow_fallbacks": True},
            "reasoning": {"effort": reasoning_effort},
        }
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
        reasoning_effort: str = "low",
    ) -> None:
        self.model = model
        self._price_in = price_in_per_mtok
        self._price_out = price_out_per_mtok
        provider = OpenRouterProvider(
            model,
            base_url=base_url,
            api_key=api_key,
            provider_order=provider_order,
            reasoning_effort=reasoning_effort,
        )
        self._provider = provider
        self._client = AsyncSystemOneAdapterClient(
            structured_outputs=True,
            llm_answer_mode="probabilities",
            normalize_probabilities=True,
            n_retry_malformed_structure=2,
            model=provider,
        )
        self.last_note: str | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> LLMDecider:
        if settings.open_router_api_key is None:
            raise ValueError("OPEN_ROUTER_API_KEY is required for the LLM decider")
        return cls(
            model=settings.llm_model,
            base_url=settings.openrouter_base_url,
            api_key=settings.open_router_api_key.get_secret_value(),
            provider_order=settings.openrouter_provider_order,
            price_in_per_mtok=settings.llm_price_in_per_mtok,
            price_out_per_mtok=settings.llm_price_out_per_mtok,
        )

    async def run(self, request: ClefRequest) -> ClefResponse:
        self.last_note = (
            f"dropped {len(request.images)} image(s): text-only model" if request.images else None
        )
        body = request.body()
        try:
            result = await self._client.system_one(body["state"], body["questions"])
        except TypeSafeError as exc:
            raise ClefTransientError(f"LLM decider failed: {exc}") from exc
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
