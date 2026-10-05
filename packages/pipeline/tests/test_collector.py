from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from debugassist.core.evidence import EvidenceItem
from debugassist.core.policy import PolicyGate
from debugassist.decisions.engine import RunContext
from debugassist.decisions.policy import Band, Verdict
from debugassist.integrations.jira import JiraMock
from debugassist.pipeline import collector, nodes
from debugassist.pipeline.state import Issue, RunState


def item(i: int, chars: int, source: Any = "logs") -> EvidenceItem:
    return EvidenceItem(
        id=f"ev_{source}_{i:010d}",
        source=source,
        kind="k",
        summary=f"window {i}",
        data={"evidence_id": f"ev_{source}_{i:010d}", "x": "y" * chars},
    )


def fake_deps(engine: Any) -> Any:
    return SimpleNamespace(engine=engine)


def bug_issue() -> Issue:
    return Issue(
        source="bugdrop",
        id="BD-1002",
        url="http://bugdrop/reports/BD-1002",
        title="app went blank after tapping the notification",
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
        report={"description": "app went blank after tapping the notification"},
    )


class D3Engine:
    """Scores: window 1 decisive (keep), 2 related (keep_if_budget), 3 irrelevant (drop), 4 related."""

    async def decide(self, decision_id: str, state: Any, **kw: Any) -> Any:
        assert decision_id == "D03"
        ids = [w["id"] for w in kw["params"]["windows"]]
        scores = dict(zip(ids, [4.0, 2.5, 0.2, 2.0], strict=True))
        acts = dict(zip(ids, ["keep", "keep_if_budget", "drop", "keep_if_budget"], strict=True))
        items = {i: Verdict(p=0.5, chosen=None, band=Band.ACT, action=acts[i]) for i in ids}
        return SimpleNamespace(
            chosen={f"relevance.{i}": s for i, s in scores.items()}, items=items, ledger_id="d3"
        )


async def test_d3_keeps_by_action_then_score_within_budget() -> None:
    core = [item(0, 700, "vitals")]
    opt = [item(1, 700), item(2, 700), item(3, 700), item(4, 700)]
    budget = collector.tokens(core[0]) + collector.tokens(opt[0]) + collector.tokens(opt[1]) + 5
    kept, pruned, ledger = await collector.score_and_fit(
        bug_issue(), core, opt, fake_deps(D3Engine()), RunContext(), budget
    )
    assert [k.summary for k in kept] == [
        "window 0",
        "window 1",
        "window 2",
    ]  # core, keep, best keep_if_budget
    reasons = {p["summary"]: p["reason"] for p in pruned}
    assert reasons == {"window 3": "not relevant", "window 4": "over budget"} and ledger == "d3"


async def test_no_optional_windows_means_no_d3_call() -> None:
    core = [item(0, 10, "vitals")]
    kept, pruned, ledger = await collector.score_and_fit(bug_issue(), core, [], fake_deps(None), RunContext())  # pyright: ignore[reportArgumentType]
    assert kept == core and pruned == [] and ledger is None


class TriageEngine:
    async def decide(self, decision_id: str, state: Any, **kw: Any) -> Any:
        if decision_id == "D01":
            return SimpleNamespace(
                chosen={"priority": 3.0, "severity": 3.0, "owning_team": "rider-app"},
                probabilities={"customer_impacting": {"true": 0.9}, "worth_agent_run": {"true": 0.8}},
                ledger_id="d1",
            )
        assert decision_id == "D02"
        assert {c["id"] for c in kw["params"]["candidates"]} == {"VIT-1001", "none"}
        return SimpleNamespace(
            chosen={"duplicate_of": "VIT-1001"},
            p=0.93,
            band=Band.ACT,
            action="mark_duplicate",
            ledger_id="d2",
        )


async def test_duplicate_report_attaches_to_the_open_ticket_and_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jira = JiraMock(tmp_path / "jira")
    existing = jira.create("[P1] crash", [("para", "x")], "P1", ["vitals-vit-1001"])

    async def candidates(issue: Issue, deps: Any, k: int = 8) -> list[dict[str, str]]:
        return [{"id": "VIT-1001", "description": "Vitals crash: TypeError … riderId"}]

    monkeypatch.setattr(collector, "dedup_candidates", candidates)
    deps = SimpleNamespace(
        engine=TriageEngine(),
        catalog={"teams": {"rider-app": {"description": "rider app", "oncall": ["a"]}}},
        gate=PolicyGate(mode="autonomous", audit_path=tmp_path / "audit.jsonl"),
        jira=jira,
        vitals_url="http://vitals",
    )
    out = await nodes.auto_triage(RunState(run_id="r1", issue_ref="BD-1002", issue=bug_issue()), deps)  # pyright: ignore[reportArgumentType]
    assert out["status"] == "duplicate" and out["triage"].duplicate_of == "VIT-1001"
    assert out["triage"].jira_key == existing.key and out["decisions"] == ["d1", "d2"]
    assert "duplicate of VIT-1001" in jira.snapshot(existing.key)["comments"][0]["text"]


def test_dedup_only_considers_older_issues() -> None:
    assert collector._older("2026-10-04T08:41:05+00:00", "2026-10-04T10:09:25+00:00")  # pyright: ignore[reportPrivateUsage]
    assert not collector._older("2026-10-04T10:09:25Z", "2026-10-04T08:41:05Z")  # pyright: ignore[reportPrivateUsage]
    assert collector._older(None, "2026-10-04T08:41:05Z")  # pyright: ignore[reportPrivateUsage]


class LowScores:
    """Everything below the keep threshold: background (1.4, 1.1) and irrelevant (0.3)."""

    async def decide(self, decision_id: str, state: Any, **kw: Any) -> Any:
        ids = [w["id"] for w in kw["params"]["windows"]]
        scores = dict(zip(ids, [1.4, 0.3, 1.1], strict=True))
        items = {i: Verdict(p=0.2, chosen=None, band=Band.SAFE_DEFAULT, action="drop") for i in ids}
        return SimpleNamespace(
            chosen={f"relevance.{i}": s for i, s in scores.items()}, items=items, ledger_id="d3"
        )


async def test_leftover_budget_goes_to_background_windows_not_irrelevant_ones() -> None:
    core = [item(0, 100, "vitals")]
    kept, pruned, _ = await collector.score_and_fit(
        bug_issue(), core, [item(1, 100), item(2, 100), item(3, 100)], fake_deps(LowScores()), RunContext()
    )
    assert [k.summary for k in kept] == ["window 0", "window 1", "window 3"]
    assert pruned == [
        {
            "id": item(2, 100).id,
            "summary": "window 2",
            "score": 0.3,
            "tokens": collector.tokens(item(2, 100)),
            "reason": "not relevant",
        }
    ]
