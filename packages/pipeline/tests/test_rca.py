from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from debugassist.core.evidence import EvidenceItem
from debugassist.decisions.policy import Band, Verdict
from debugassist.llm.spec import LLMResult, ToolCall
from debugassist.pipeline import rca
from debugassist.pipeline.state import Claim, CodeLocation, Issue, RCAOutput, RunState


def issue() -> Issue:
    return Issue(
        source="bugdrop",
        id="BD-1002",
        url="http://bugdrop/reports/BD-1002",
        title="battery drained while the app was in the background",
        kind="bug_report",
        app="miniride-client",
        platform="iOS 17.5",
        version="1.6.1",
        first_version="1.6.1",
        last_version="1.6.1",
        repo="miniride-client",
        gh_repo="IshaanNene/miniride-client",
        component=".",
        language="typescript",
    )


def state(evidence: list[EvidenceItem] | None = None) -> RunState:
    return RunState(run_id="r1", issue_ref="BD-1002", issue=issue(), evidence=evidence or [])


def ev(i: int) -> EvidenceItem:
    eid = f"ev_metrics_{i:010d}"
    return EvidenceItem(id=eid, source="metrics", kind="k", summary=f"item {i}", data={"evidence_id": eid})


def verdict(action: str, p: float) -> Verdict:
    return Verdict(p=p, chosen=None, band=Band.ACT, action=action)


class D9Engine:
    """Keeps claims whose text says 'true', drops the rest; records what each call saw."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def decide(self, decision_id: str, cs: Any, **kw: Any) -> Any:
        assert decision_id == "D09"
        [claim] = kw["params"]["claims"]
        self.calls.append({"claim": claim, "state": cs})
        action = "keep" if "true" in claim["text"] else "drop"
        return SimpleNamespace(items={claim["id"]: verdict(action, 0.9)}, ledger_id=f"l{claim['id']}")


async def test_ground_claims_makes_one_call_per_claim_with_only_its_citations() -> None:
    lookup = {"ev_a": "A body", "ev_b": "B body"}
    out = RCAOutput(
        category="own_code",
        summary="s",
        root_cause="r",
        location=CodeLocation(repo="miniride-client", file="f.ts", function="tick"),
        timeline=[],
        reproduction="r",
        fix_direction="f",
        claims=[
            Claim(text="true thing", evidence_ids=["ev_a"]),
            Claim(text="false thing", evidence_ids=["ev_b"]),
            Claim(text="true but cites nothing real", evidence_ids=["ev_made_up"]),
        ],
    )
    engine = D9Engine()
    kept, verdicts, dropped, ledgers = await rca.ground_claims(
        state(),
        SimpleNamespace(engine=engine),  # pyright: ignore[reportArgumentType]
        out,
        lookup,
    )
    assert [c.text for c in kept.claims] == ["true thing"]
    assert [c.text for c in dropped] == ["false thing", "true but cites nothing real"]
    assert [v["grounding"] for v in verdicts] == ["supported", "unsupported", "unsupported"]
    assert len(engine.calls) == 2 and ledgers == ["lc1", "lc2"]  # the fabricated citation costs no call
    assert "B body" not in str(engine.calls[0]["state"].render(10_000))


def test_evidence_lookup_prefers_the_fuller_tool_text() -> None:
    call = ToolCall(
        name="read_file",
        args={},
        ok=True,
        result_preview="short",
        ms=1,
        evidence_id="ev_code_1",
        evidence_text="x" * 9000,
    )
    r = LLMResult(node="n", output=None, status="ok", turns=1, tool_calls=[call], model="m", mode="mock")
    lookup = rca.evidence_lookup(state([ev(1)]), [r])
    assert set(lookup) == {"ev_metrics_0000000001", "ev_code_1"}
    assert len(lookup["ev_code_1"]) == len("read_file result: ") + rca.GROUNDING_CHARS


class D7Engine:
    async def decide(self, decision_id: str, cs: Any, **kw: Any) -> Any:
        assert decision_id == "D07"
        ids = [s["id"] for s in kw["params"]["subagents"]]
        items = {i: verdict("skip", 0.1) for i in ids}
        items.update(
            {
                "perf-profiler": verdict("spawn", 0.9),
                "log-analyst": verdict("spawn", 0.95),
                "trace-analyst": verdict("spawn_if_budget", 0.6),
                "code-localizer": verdict("spawn_if_budget", 0.7),
                "commit-bisector": verdict("spawn_if_budget", 0.5),
            }
        )
        return SimpleNamespace(items=items, ledger_id="d7")


async def test_pick_subagents_spawns_first_then_fills_by_probability_up_to_the_cap() -> None:
    chosen, ps, ledger = await rca.pick_subagents(state(), SimpleNamespace(engine=D7Engine()))  # pyright: ignore[reportArgumentType]
    assert chosen == ["log-analyst", "perf-profiler", "code-localizer", "trace-analyst"]
    assert ps["commit-bisector"] == 0.5 and ledger == "d7"


class D6Engine:
    def __init__(self, answers: list[tuple[str, str]]) -> None:
        self.answers = answers
        self.offered: list[list[str]] = []

    async def decide(self, decision_id: str, cs: Any, **kw: Any) -> Any:
        assert decision_id == "D06"
        self.offered.append([s["id"] for s in kw["params"]["sources"]])
        action, source = self.answers.pop(0)
        return SimpleNamespace(chosen={"next_source": source}, p=0.8, action=action, ledger_id="d6")


async def test_evidence_loop_fetches_what_clef_asks_for_and_never_offers_it_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_fetchers(_issue: Issue, _deps: Any) -> dict[str, tuple[str, rca.Fetcher]]:
        return {"session_perf": ("perf", lambda: ev(7)), "incidents": ("inc", lambda: ev(8))}

    monkeypatch.setattr(rca, "fetchers", fake_fetchers)
    engine = D6Engine([("fetch_more", "session_perf"), ("enough", "")])
    added, rounds, ledgers = await rca.evidence_loop(state(), SimpleNamespace(engine=engine))  # pyright: ignore[reportArgumentType]
    assert [a.summary for a in added] == ["item 7"]
    assert engine.offered == [["session_perf", "incidents"], ["incidents"]]
    assert [r["action"] for r in rounds] == ["fetch_more", "enough"] and ledgers == ["d6", "d6"]


async def test_evidence_loop_stops_on_an_unknown_source(monkeypatch: pytest.MonkeyPatch) -> None:
    def one_fetcher(_issue: Issue, _deps: Any) -> dict[str, tuple[str, rca.Fetcher]]:
        return {"incidents": ("inc", lambda: ev(8))}

    monkeypatch.setattr(rca, "fetchers", one_fetcher)
    engine = D6Engine([("fetch_more", "made_up_source")])
    added, rounds, _ = await rca.evidence_loop(state(), SimpleNamespace(engine=engine))  # pyright: ignore[reportArgumentType]
    assert added == [] and len(rounds) == 1
