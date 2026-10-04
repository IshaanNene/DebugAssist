"""Clef / Clef-flash on Cloudflare Workers AI (REST)."""

from __future__ import annotations

import httpx

from debugassist.core.settings import Mode
from debugassist.decisions.backends.base import WORKERS_AI_PRICE_PER_MTOK
from debugassist.decisions.resilience import RetryPolicy, with_retries
from debugassist.decisions.schema import (
    ClefRequest,
    ClefRequestError,
    ClefResponse,
    ClefTransientError,
    parse_response,
)

API = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/cloudflare/{model}"


class WorkersAIClef:
    name = "workers_ai"
    mode = Mode.LIVE

    def __init__(
        self,
        account_id: str,
        api_token: str,
        *,
        timeout_s: float = 20.0,
        retry: RetryPolicy | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._account = account_id
        self._retry = retry or RetryPolicy()
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"},
            timeout=httpx.Timeout(timeout_s, connect=5.0),
            transport=transport,
        )

    def url(self, model: str) -> str:
        return API.format(account=self._account, model=model)

    async def _once(self, request: ClefRequest) -> ClefResponse:
        try:
            resp = await self._client.post(self.url(request.model), content=request.body_bytes())
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise ClefTransientError(f"{type(exc).__name__}: {exc}") from exc
        if resp.status_code == 429 or resp.status_code >= 500:
            raise ClefTransientError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        if resp.status_code >= 400:
            raise ClefRequestError(f"HTTP {resp.status_code}: {resp.text[:500]}")
        parsed = parse_response(resp.json())
        parsed.check_against(request)
        return parsed

    async def run(self, request: ClefRequest) -> ClefResponse:
        return await with_retries(lambda: self._once(request), self._retry)

    def cost_usd(self, response: ClefResponse) -> float:
        price = WORKERS_AI_PRICE_PER_MTOK.get(response.model, WORKERS_AI_PRICE_PER_MTOK["clef"])
        return response.usage.input_tokens * price / 1_000_000

    async def aclose(self) -> None:
        await self._client.aclose()
