"""ROADMAP-100 028: every conditional edge of the fixed plan, with every way out of it.

The edges are read from the built graph, so adding a node or an edge without a row here fails
`test_every_edge_has_cases`."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from langgraph.graph import END

from debugassist.pipeline import graph, nodes
from debugassist.pipeline.state import FixPlan, Mitigation, RunState

FIXTURE = Path(__file__).parent / "fixtures" / "run_state.json"


def base() -> RunState:
    s = RunState.model_validate(json.loads(FIXTURE.read_text()))
    return s.model_copy(update={"status": "running"})


def with_rca(category: str, d05: str | None = None, actionable: bool = True) -> RunState:
    s = base()
    assert s.rca and s.rca.output
    rca = s.rca.model_copy(
        update={
            "output": s.rca.output.model_copy(update={"category": category}),
            "actionable": actionable,
            "category_decision": {"chosen": {"category": d05 or category}},
        }
    )
    return s.model_copy(update={"rca": rca})


def status(st: str) -> RunState:
    return base().model_copy(update={"status": st})


LINEAR = {"ingest": "auto_triage", "auto_triage": "context_collector", "context_collector": "classify_rca",
          "ship_gate": "pr_and_notify", "pr_and_notify": "post_merge_watch"}  # fmt: skip
CASES: dict[str, list[tuple[str, Any, str]]] = {
    **{
        src: [
            ("running", base(), dst),
            ("failed", status("failed"), END),
            ("duplicate", status("duplicate"), END),
            ("stopped", status("stopped"), END),
        ]
        for src, dst in LINEAR.items()
    },
    "classify_rca": [
        ("own code", with_rca("own_code"), "mitigate"),
        ("routed, D05 agrees", with_rca("infra"), "ship_gate"),
        ("routed, D05 disagrees", with_rca("infra", d05="own_code"), "mitigate"),
        ("not actionable", with_rca("own_code", actionable=False), "ship_gate"),
        ("failed", status("failed"), END),
        ("stopped", status("stopped"), END),
    ],
    "mitigate": [
        (
            "flag config rolled back",
            with_rca("flag_config").model_copy(
                update={"mitigation": Mitigation(flag="f", action="rolled_back")}
            ),
            "ship_gate",
        ),
        (
            "flag config, nothing to roll back",
            with_rca("flag_config").model_copy(update={"mitigation": Mitigation(action="none")}),
            "fix",
        ),
        ("own code", with_rca("own_code"), "fix"),
        ("failed", status("failed"), END),
        ("duplicate", status("duplicate"), END),
    ],
    "fix": [
        (
            "plan skipped",
            base().model_copy(update={"fix_plan": FixPlan(skip="needs a human: x")}),
            "ship_gate",
        ),
        ("fixed", base().model_copy(update={"fix_plan": None}), "validate"),
        ("failed", status("failed"), END),
    ],
    "validate": [
        ("retry", ("retry", True), "fix"),
        ("no retry", ("retry", False), "ship_gate"),
        ("failed", status("failed"), END),
    ],
}


def _route(src: str, state: Any, monkeypatch: pytest.MonkeyPatch) -> str:
    if isinstance(state, tuple):  # validate: D15 decides; the state is the fixture's
        retry = bool(cast(tuple[str, bool], state)[1])

        async def decide(s: RunState, deps: Any) -> bool:
            return retry

        monkeypatch.setattr(nodes, "decide_retry", decide)
        state = base()
    g = graph.build_graph(cast(Any, SimpleNamespace()), log=lambda _: None)
    [spec] = g.branches[src].values()
    return str(asyncio.run(spec.path.ainvoke(state)))


def test_every_edge_has_cases() -> None:
    g = graph.build_graph(cast(Any, SimpleNamespace()), log=lambda _: None)
    assert set(g.branches) == set(CASES)


@pytest.mark.parametrize(
    ("src", "case", "state", "dst"),
    [(src, name, st, dst) for src, rows in CASES.items() for name, st, dst in rows],
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_edge(src: str, case: str, state: Any, dst: str, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _route(src, state, monkeypatch) == dst, case
