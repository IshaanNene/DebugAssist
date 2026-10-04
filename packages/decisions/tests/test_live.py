"""Live checks against real APIs. Run with DA_LIVE_TESTS=1 (cost: well under $0.01)."""

import pytest

from debugassist.core.settings import Settings
from debugassist.decisions.factory import build_engine

pytestmark = pytest.mark.live
STATE = {
    "error": "TypeError: Cannot read properties of undefined (reading 'session') at routeDeepLink",
    "flag": "notif_router_v2 at 5% rollout; every crash session is flag-exposed",
}


@pytest.mark.parametrize("model", ["clef", "clef-flash"])
async def test_workers_ai_decision(model: str) -> None:
    engine = await build_engine(Settings(), "clef", with_ledger=False, second_opinion=False)
    try:
        d = await engine.decide("D05", STATE, model=model)  # pyright: ignore[reportArgumentType]
    finally:
        await engine.aclose()
    assert d.backend == "workers_ai" and d.fallback_reason is None
    assert d.model == model and d.input_tokens > 0
    assert abs(sum(d.probabilities["category"].values()) - 1) < 1e-2


async def test_llm_baseline_decision() -> None:
    engine = await build_engine(Settings(), "llm", with_ledger=False, second_opinion=False)
    try:
        d = await engine.decide("D05", STATE)
    finally:
        await engine.aclose()
    assert d.backend == "llm" and d.model == "openai/gpt-oss-120b"
    assert d.chosen["category"] in d.probabilities["category"]
