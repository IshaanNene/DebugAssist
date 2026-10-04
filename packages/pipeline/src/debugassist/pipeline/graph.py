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

from debugassist.pipeline import nodes
from debugassist.pipeline.deps import Deps
from debugassist.pipeline.state import RunState

Node = Callable[[RunState, Deps], Awaitable[dict[str, Any]]]

NODE_KIND = {  # for the run view: deterministic, llm, decision-heavy
    "ingest": "deterministic",
    "auto_triage": "deterministic+clef",
    "context_collector": "deterministic",
    "classify_rca": "llm+clef",
    "mitigate": "deterministic+clef",
    "fix": "llm",
    "validate": "deterministic",
    "ship_gate": "clef",
    "pr_and_notify": "deterministic",
    "post_merge_watch": "deterministic",
}


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
        t0 = time.perf_counter()
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
        ms = int((time.perf_counter() - t0) * 1000)
        update["timings_ms"] = {**state.timings_ms, name: ms}
        _persist(deps, state, name, update, ms)
        return update

    return node


def build_graph(deps: Deps, log: Callable[[str], None] = print) -> StateGraph[RunState]:
    g: StateGraph[RunState] = StateGraph(RunState)
    for name in NODE_KIND:
        g.add_node(name, cast(Any, wrap(name, getattr(nodes, name), deps, log)))  # pyright: ignore[reportUnknownMemberType]

    def ok(next_node: str) -> Callable[[RunState], str]:
        return lambda s: END if s.status == "failed" else next_node

    def after_rca(s: RunState) -> str:
        if s.status == "failed":
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
    g.add_conditional_edges("fix", ok("validate"))

    async def after_validate(s: RunState) -> str:
        if s.status == "failed":
            return END
        return "fix" if await nodes.decide_retry(s, deps) else "ship_gate"

    g.add_conditional_edges("validate", after_validate)
    g.add_conditional_edges("ship_gate", ok("pr_and_notify"))
    g.add_conditional_edges("pr_and_notify", ok("post_merge_watch"))
    g.add_edge("post_merge_watch", END)
    return g
