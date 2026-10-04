"""Retries with exponential backoff, a circuit breaker, and primary→fallback routing."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from debugassist.core.settings import Mode
from debugassist.decisions.backends.base import DecisionBackend
from debugassist.decisions.schema import ClefError, ClefRequest, ClefResponse, ClefTransientError


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_s: float = 0.25
    max_delay_s: float = 4.0
    jitter: float = 0.25


async def with_retries[T](call: Callable[[], Awaitable[T]], policy: RetryPolicy) -> T:
    """Retry only ``ClefTransientError`` (timeouts, 429, 5xx); everything else propagates at once."""
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await call()
        except ClefTransientError:
            if attempt == policy.max_attempts:
                raise
            delay = min(policy.max_delay_s, policy.base_delay_s * 2 ** (attempt - 1))
            await asyncio.sleep(delay * (1 + random.uniform(-policy.jitter, policy.jitter)))  # noqa: S311
    raise AssertionError("unreachable")


@dataclass
class CircuitBreaker:
    """Opens after ``threshold`` consecutive failures; half-opens after ``cooldown_s``."""

    threshold: int = 3
    cooldown_s: float = 30.0
    clock: Callable[[], float] = time.monotonic
    _failures: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        return self.clock() - self._opened_at < self.cooldown_s  # after cooldown: half-open

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.threshold:
            self._opened_at = self.clock()


class FallbackBackend:
    """Use ``primary`` unless its breaker is open or it fails; then answer with ``fallback``.

    ``last_fallback_reason`` is set on the instance after each call (None when primary answered),
    so the engine can record it in the ledger.
    """

    def __init__(
        self, primary: DecisionBackend, fallback: DecisionBackend, breaker: CircuitBreaker | None = None
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.breaker = breaker or CircuitBreaker()
        self.name = primary.name
        self.mode: Mode = primary.mode
        self.last_backend: DecisionBackend = primary
        self.last_fallback_reason: str | None = None

    async def run(self, request: ClefRequest) -> ClefResponse:
        if self.breaker.is_open:
            return await self._fall_back(request, "circuit open")
        try:
            response = await self.primary.run(request)
        except ClefError as exc:
            self.breaker.record_failure()
            return await self._fall_back(request, f"{type(exc).__name__}: {exc}"[:500])
        self.breaker.record_success()
        self.last_backend, self.last_fallback_reason = self.primary, None
        return response

    async def _fall_back(self, request: ClefRequest, reason: str) -> ClefResponse:
        self.last_backend, self.last_fallback_reason = self.fallback, reason
        return await self.fallback.run(request)

    def cost_usd(self, response: ClefResponse) -> float:
        return self.last_backend.cost_usd(response)

    async def aclose(self) -> None:
        await self.primary.aclose()
        await self.fallback.aclose()
