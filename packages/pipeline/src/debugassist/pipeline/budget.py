"""The global run budget (SPEC §10): LLM spend (per node, in `state.costs`) plus Clef spend (the ledger)
against the agent type's `run_budget_usd`. LLM nodes do not start once it is spent, and each agent's own
cap (`max_budget_usd`) is lowered to what is left."""

from __future__ import annotations

from typing import Any

from debugassist.pipeline.deps import Deps
from debugassist.pipeline.state import RunState


async def spent(state: RunState, deps: Deps) -> dict[str, float]:
    clef = 0.0
    if deps.engine.ledger is not None:
        clef = sum(float(r.cost_usd) for r in await deps.engine.ledger.list(run_id=state.run_id))
    llm = sum(state.costs.values())
    return {"llm": round(llm, 6), "clef": round(clef, 6), "total": round(llm + clef, 6)}


def limit(deps: Deps) -> float:
    return float(deps.agent_type.get("run_budget_usd", 3.0))


def cap(cfg: dict[str, Any], deps: Deps) -> dict[str, Any]:
    """The node's limits with max_budget_usd lowered to the run budget still available."""
    left = deps.extra.get("budget_remaining")
    if left is None:
        return cfg
    return {**cfg, "max_budget_usd": max(0.0, min(float(cfg.get("max_budget_usd", left)), float(left)))}
