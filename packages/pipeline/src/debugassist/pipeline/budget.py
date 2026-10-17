"""The global run budget (SPEC §10): LLM spend (per node, in `state.costs`) plus Clef spend (the ledger)
against the agent type's `run_budget_usd`. LLM nodes do not start once it is spent, and each agent's own
cap (`max_budget_usd`) is lowered to what is left."""

from __future__ import annotations

import os
from typing import Any

from debugassist.pipeline.deps import Deps
from debugassist.pipeline.state import RunState


async def spent(state: RunState, deps: Deps) -> dict[str, float]:
    clef = 0.0
    if deps.engine.ledger is not None:
        clef = sum(float(r.cost_usd) for r in await deps.engine.ledger.list(run_id=state.run_id))
    llm = sum(state.costs.values())
    return {"llm": round(llm, 6), "clef": round(clef, 6), "total": round(llm + clef, 6)}


HARD_CAP_USD = (
    5.0  # no single run spends more without someone raising DA_RUN_BUDGET_CAP_USD (CLAUDE.md: ask above $5)
)


def limit(deps: Deps, state: RunState | None = None) -> float:
    """The run's budget: the agent type's, lowered by the repository's own `run_budget_usd` (ROADMAP-100 075) and
    by the global cap `DA_RUN_BUDGET_CAP_USD` (default $5)."""
    caps = [
        float(deps.agent_type.get("run_budget_usd", 3.0)),
        float(os.environ.get("DA_RUN_BUDGET_CAP_USD") or HARD_CAP_USD),
    ]
    if state is not None and state.issue is not None and state.issue.run_budget_usd is not None:
        caps.append(float(state.issue.run_budget_usd))
    return min(caps)


def cap(cfg: dict[str, Any], deps: Deps) -> dict[str, Any]:
    """The node's limits with max_budget_usd lowered to the run budget still available."""
    left = deps.extra.get("budget_remaining")
    if left is None:
        return cfg
    return {**cfg, "max_budget_usd": max(0.0, min(float(cfg.get("max_budget_usd", left)), float(left)))}
