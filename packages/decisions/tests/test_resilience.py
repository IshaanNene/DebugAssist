from typing import Any

import pytest

from debugassist.core.settings import Mode
from debugassist.decisions.backends.mock import MockDecider
from debugassist.decisions.resilience import CircuitBreaker, FallbackBackend
from debugassist.decisions.schema import ClefRequest, ClefResponse, ClefTransientError


class Failing:
    name = "workers_ai"
    mode = Mode.LIVE

    def __init__(self) -> None:
        self.calls = 0

    async def run(self, request: ClefRequest) -> ClefResponse:
        self.calls += 1
        raise ClefTransientError("down")

    def cost_usd(self, response: ClefResponse) -> float:
        return 1.0

    async def aclose(self) -> None:
        return None


@pytest.fixture
def req(basic_questions: dict[str, Any]) -> ClefRequest:
    return ClefRequest.model_validate({"model": "clef", "state": "s", "questions": basic_questions})


def test_breaker_opens_and_half_opens() -> None:
    now = [0.0]
    b = CircuitBreaker(threshold=2, cooldown_s=10, clock=lambda: now[0])
    b.record_failure()
    assert not b.is_open
    b.record_failure()
    assert b.is_open
    now[0] = 10.0
    assert not b.is_open
    b.record_success()
    assert not b.is_open


async def test_fallback_on_failure_then_circuit_open(req: ClefRequest) -> None:
    primary = Failing()
    fb = FallbackBackend(primary, MockDecider(), CircuitBreaker(threshold=2, cooldown_s=60))
    await fb.run(req)
    assert fb.last_backend.name == "mock" and "down" in (fb.last_fallback_reason or "")
    await fb.run(req)
    await fb.run(req)  # breaker now open: primary not called again
    assert primary.calls == 2
    assert fb.last_fallback_reason == "circuit open"
    assert fb.cost_usd(await fb.run(req)) == 0.0


async def test_concurrent_calls_are_attributed_to_the_backend_that_served_each(req: ClefRequest) -> None:
    """Audit P3-17: `last_backend` was read after concurrent awaits, so a ledger row could name another call's
    backend. `serve` returns the attribution with the response."""
    import asyncio

    class Slow:
        name, mode = "workers_ai", Mode.LIVE

        def __init__(self) -> None:
            self.n = 0

        async def run(self, request: ClefRequest) -> ClefResponse:
            self.n += 1
            if self.n == 1:  # the first call fails late, after the second has succeeded
                await asyncio.sleep(0.05)
                raise ClefTransientError("down")
            return await MockDecider().run(request)

        def cost_usd(self, response: ClefResponse) -> float:
            return 1.0

        async def aclose(self) -> None:
            return None

    fb = FallbackBackend(Slow(), MockDecider(), CircuitBreaker(threshold=5))
    (_, first, why1), (_, second, why2) = await asyncio.gather(fb.serve(req), fb.serve(req))
    assert (first.name, second.name) == ("mock", "workers_ai")
    assert "down" in (why1 or "") and why2 is None
