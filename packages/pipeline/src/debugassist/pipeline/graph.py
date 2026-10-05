"""The fixed plan (ADR 0001): the LLM never chooses the next step.

ingest → auto_triage → context_collector → classify_rca ─(not actionable)→ ship_gate
                                                     └→ mitigate → fix → validate ─(retry ≤ cap, D15)→ fix
                                                                              └→ ship_gate → pr_and_notify → post_merge_watch
"""

from __future__ import annotations

import json
import time
import traceback
from collections.abc import Awaitable, Callable
from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from debugassist.core import tracing
from debugassist.pipeline import budget, nodes
from debugassist.pipeline.deps import Deps
from debugassist.pipeline.state import NODE_KIND, RunState

Node = Callable[[RunState, Deps], Awaitable[dict[str, Any]]]


def _persist(deps: Deps, state: RunState, node: str, update: dict[str, Any], ms: int) -> None:
    d = deps.run_dir
    (d / "nodes").mkdir(parents=True, exist_ok=True)
    (d / "nodes" / f"{len(list((d / 'nodes').glob('*.json'))):02d}-{node}.json").write_text(
        json.dumps(
            {"node": node, "kind": NODE_KIND.get(node), "ms": ms, "update": update},
            indent=2,
            default=lambda o: o.model_dump(mode="json") if hasattr(o, "model_dump") else str(o),
        )
    )
    merged = state.model_copy(update=update)
    (d / "state.json").write_text(merged.model_dump_json(indent=2))


def wrap(
    name: str, fn: Node, deps: Deps, log: Callable[[str], None]
) -> Callable[[RunState], Awaitable[dict[str, Any]]]:
    async def node(state: RunState) -> dict[str, Any]:
        log(f"▶ {name}")
        if state.agent_type and deps.agent_type.get("name") != state.agent_type:  # resumed run
            from debugassist.harness import agent_types

            deps.agent_type = agent_types.load(state.agent_type).model_dump()
        t0 = time.perf_counter()
        kind = NODE_KIND.get(name, "deterministic")
        with tracing.span(name, kind="agent" if "llm" in kind else "chain", node=name, node_kind=kind) as sp:
            update = await _run_node(name, kind, fn, state, deps, log)
            tracing.set_attributes(
                sp,
                status=update.get("status", "ok"),
                error=(update.get("errors") or [None])[-2] if update.get("status") == "failed" else None,
            )
        trace_id = deps.extra.get("trace_id")
        if trace_id and trace_id not in state.traces:
            update["traces"] = [*state.traces, trace_id]
        ms = int((time.perf_counter() - t0) * 1000)
        update["timings_ms"] = {**state.timings_ms, name: ms}
        if deps.extra.get("until") == name and update.get("status") not in ("failed", "duplicate"):
            update["status"] = "stopped"  # --until: end the run after this step
            update["stopped_after"] = name
        _persist(deps, state, name, update, ms)
        return update

    return node


async def _run_node(
    name: str, kind: str, fn: Node, state: RunState, deps: Deps, log: Callable[[str], None]
) -> dict[str, Any]:
    if "llm" in kind:  # the global run budget: no new LLM work once it is spent
        spent = await budget.spent(state, deps)
        left = budget.limit(deps) - spent["total"]
        deps.extra["budget_remaining"] = left
        if left <= 0:
            msg = f"{name}: run budget exhausted (${spent['total']:.4f} of ${budget.limit(deps):.2f})"
            log(f"  ✗ {msg}")
            return {"status": "failed", "errors": [*state.errors, msg, ""]}
    try:
        update = await fn(state, deps)
    except Exception as exc:
        if type(exc).__name__ == "GraphInterrupt":
            raise
        update: dict[str, Any] = {
            "status": "failed",
            "errors": [
                *state.errors,
                f"{name}: {type(exc).__name__}: {exc}",
                traceback.format_exc()[-2000:],
            ],
        }
        log(f"  ✗ {name}: {exc}")
    return update


def build_graph(deps: Deps, log: Callable[[str], None] = print) -> StateGraph[RunState]:
    g: StateGraph[RunState] = StateGraph(RunState)
    for name in NODE_KIND:
        g.add_node(name, cast(Any, wrap(name, getattr(nodes, name), deps, log)))  # pyright: ignore[reportUnknownMemberType]

    def ok(next_node: str) -> Callable[[RunState], str]:
        return lambda s: END if s.status in ("failed", "duplicate", "stopped") else next_node

    def after_rca(s: RunState) -> str:
        if s.status in ("failed", "stopped"):
            return END
        return "mitigate" if s.rca and s.rca.actionable else "ship_gate"

    g.add_edge(START, "ingest")
    g.add_conditional_edges("ingest", ok("auto_triage"))
    g.add_conditional_edges("auto_triage", ok("context_collector"))
    g.add_conditional_edges("context_collector", ok("classify_rca"))
    g.add_conditional_edges(
        "classify_rca",
        after_rca,
    )
    g.add_conditional_edges("mitigate", ok("fix"))

    def after_fix(s: RunState) -> str:
        if s.status in ("failed", "stopped"):
            return END
        return "ship_gate" if s.fix_plan and s.fix_plan.skip else "validate"

    g.add_conditional_edges("fix", after_fix)

    async def after_validate(s: RunState) -> str:
        if s.status in ("failed", "stopped"):
            return END
        return "fix" if await nodes.decide_retry(s, deps) else "ship_gate"

    g.add_conditional_edges("validate", after_validate)
    g.add_conditional_edges("ship_gate", ok("pr_and_notify"))
    g.add_conditional_edges("pr_and_notify", ok("post_merge_watch"))
    g.add_edge("post_merge_watch", END)
    return g
