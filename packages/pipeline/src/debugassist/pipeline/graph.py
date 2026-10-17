"""The fixed plan (ADR 0001): the LLM never chooses the next step.

ingest → auto_triage → context_collector → classify_rca ─(not actionable, or not our code)→ ship_gate
                                                     └→ mitigate ─(the flag itself is the defect, rollback proposed)→ ship_gate
                                                            └→ fix → validate ─(retry ≤ cap, D15)→ fix
                                                                         └→ ship_gate → pr_and_notify → post_merge_watch

Routing reads both Clef's category decision taken before the RCA (D05, `rca.actionable`) and the category the
RCA itself arrived at with the full evidence: a root cause that is not a code change in our repos is reported
and routed, never patched.
"""

from __future__ import annotations

import json
import time
import traceback
from collections.abc import Awaitable, Callable
from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from debugassist.core import runctx, tracing
from debugassist.core.files import write_atomic
from debugassist.core.redaction import redact, redact_secrets
from debugassist.pipeline import budget, nodes
from debugassist.pipeline.deps import Deps
from debugassist.pipeline.state import NODE_KIND, RunState

Node = Callable[[RunState, Deps], Awaitable[dict[str, Any]]]

# RCA categories whose fix is never a code change in our repos: report and route them. `network` and
# `flag_config` are not here — a too-short timeout or a config value in our code is fixed by a pull request.
ROUTED = {"infra", "device_os", "not_a_bug", "third_party_lib"}


def rca_category(s: RunState) -> str | None:
    return s.rca.output.category if s.rca and s.rca.output else None


def routed_away(s: RunState) -> bool:
    """Whether the RCA's "not a code change in our repos" stands on its own.

    A wrong "not ours" was terminal (BUG-011 in the no-Clef arm): the RCA's category alone ends the run before any
    fix is tried. It ends it only when D05, asked before the RCA, picked the same category; when the two disagree
    the run goes on and the fix plan decides (ROADMAP-100 013). Runs without a D05 answer keep the old rule."""
    category = rca_category(s)
    if category not in ROUTED or s.rca is None:
        return False
    chosen: Any = s.rca.category_decision.get("chosen")
    d05 = cast(dict[str, Any], chosen).get("category") if isinstance(chosen, dict) else None
    return d05 is None or str(d05) == category


def after_rca(s: RunState) -> str:
    if s.status in ("failed", "stopped"):
        return END
    if not (s.rca and s.rca.actionable) or routed_away(s):
        return "ship_gate"
    return "mitigate"


def after_mitigate(s: RunState) -> str:
    if s.status in ("failed", "duplicate", "stopped"):
        return END
    # The flag's configuration is the defect and a rollback was decided (D11): there is no code to change.
    if rca_category(s) == "flag_config" and s.mitigation and s.mitigation.action != "none":
        return "ship_gate"
    return "fix"


def _persist(deps: Deps, state: RunState, node: str, update: dict[str, Any], ms: int) -> None:
    """Node file and state.json, written atomically and with credentials masked in every string (ROADMAP-100 058):
    whatever a tool, a model or an exception put in the state, these files are what the API serves."""
    d = deps.run_dir
    (d / "nodes").mkdir(parents=True, exist_ok=True)

    def plain(o: Any) -> Any:
        return o.model_dump(mode="json") if hasattr(o, "model_dump") else str(o)

    record = json.loads(
        json.dumps({"node": node, "kind": NODE_KIND.get(node), "ms": ms, "update": update}, default=plain)
    )
    write_atomic(
        d / "nodes" / f"{len(list((d / 'nodes').glob('*.json'))):02d}-{node}.json",
        json.dumps(redact(record, text=redact_secrets), indent=2),
    )
    merged = state.model_copy(update=update)
    write_atomic(
        d / "state.json", json.dumps(redact(merged.model_dump(mode="json"), text=redact_secrets), indent=2)
    )


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
        with (
            runctx.use(**nodes.run_values(state)),
            tracing.span(name, kind="agent" if "llm" in kind else "chain", node=name, node_kind=kind) as sp,
        ):
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
        # Errors are persisted (state.json, node files), traced and served by the API: a credential in an
        # exception (a token in a failed command's argv) must not survive into any of them.
        update: dict[str, Any] = {
            "status": "failed",
            "errors": [
                *state.errors,
                redact_secrets(f"{name}: {type(exc).__name__}: {exc}"),
                redact_secrets(traceback.format_exc()[-2000:]),
            ],
        }
        log(f"  ✗ {name}: {redact_secrets(str(exc))}")
    return update


def build_graph(deps: Deps, log: Callable[[str], None] = print) -> StateGraph[RunState]:
    g: StateGraph[RunState] = StateGraph(RunState)
    for name in NODE_KIND:
        g.add_node(name, cast(Any, wrap(name, getattr(nodes, name), deps, log)))  # pyright: ignore[reportUnknownMemberType]

    def ok(next_node: str) -> Callable[[RunState], str]:
        return lambda s: END if s.status in ("failed", "duplicate", "stopped") else next_node

    g.add_edge(START, "ingest")
    g.add_conditional_edges("ingest", ok("auto_triage"))
    g.add_conditional_edges("auto_triage", ok("context_collector"))
    g.add_conditional_edges("context_collector", ok("classify_rca"))
    g.add_conditional_edges(
        "classify_rca",
        after_rca,
    )

    g.add_conditional_edges("mitigate", after_mitigate)

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
