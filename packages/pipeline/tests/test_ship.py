# pyright: reportPrivateUsage=false, reportUnknownLambdaType=false, reportUnknownArgumentType=false
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from debugassist.core.policy import PolicyGate
from debugassist.decisions.policy import Band
from debugassist.integrations.chat import ChatMock
from debugassist.integrations.jira import JiraMock
from debugassist.pipeline import nodes, postmerge, pr_body
from debugassist.pipeline.state import PRInfo, RunState, Watch

FIXTURE = Path(__file__).parent / "fixtures" / "run_state.json"


def run_state() -> RunState:
    return RunState.model_validate(json.loads(FIXTURE.read_text()))


def test_render_drops_empty_sections_with_their_heading() -> None:
    tpl = "## A\n{{a}}\n\n## B\n{{b}}\n\n---\n{{c}}\n"
    out = pr_body.render(tpl, {"a": "alpha", "b": "", "c": "foot"})
    assert out == "## A\nalpha\n\n---\nfoot\n"


def test_pr_body_follows_the_skill_template() -> None:
    s = run_state()
    body = pr_body.pr_body(s)
    headings = [line for line in body.splitlines() if line.startswith("## ")]
    order = [
        h
        for h in (
            "## Summary",
            "## Root cause",
            "## Evidence",
            "## Mitigation",
            "## Fix",
            "## Test proof",
            "## Risk & rollback",
        )
        if h in headings
    ]
    assert headings == order and "## Summary" in headings and "## Test proof" in headings
    assert "Vitals issue [VIT-1001]" in body and "Opened by **DebugAssist**" in body
    assert "| ❌ on the release (must fail) |" in body
    assert "{{" not in body


def test_bugdrop_issues_are_described_as_reports() -> None:
    s = run_state()
    assert s.issue
    s.issue.source = "bugdrop"
    s.issue.id = "BD-1003"
    assert "BugDrop report [BD-1003]" in pr_body.pr_body(s)


def deps(tmp_path: Path, **kw: Any) -> Any:
    return SimpleNamespace(
        gate=PolicyGate(mode="autonomous", audit_path=tmp_path / "audit.jsonl"),
        chat=ChatMock(tmp_path / "inbox.jsonl"),
        jira=JiraMock(tmp_path / "jira"),
        vitals_url="http://vitals",
        bugdrop_url="http://bugdrop",
        **kw,
    )


def test_links_go_back_to_the_source_issue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    posted: list[tuple[str, Any]] = []

    def fake_post(url: str, json: Any = None, timeout: float = 0) -> Any:
        posted.append((url, json))
        return SimpleNamespace(raise_for_status=lambda: None)

    monkeypatch.setattr(nodes.httpx, "post", fake_post)
    s = run_state()
    notes = nodes._link_source(
        deps(tmp_path), s, [("pr", "https://github.com/o/r/pull/3", "PR #3"), ("jira", None, None)], "open_pr"
    )  # pyright: ignore[reportPrivateUsage]
    assert posted == [
        (
            "http://vitals/api/issues/VIT-1001/links",
            {"kind": "pr", "url": "https://github.com/o/r/pull/3", "title": "PR #3"},
        )
    ]
    assert notes[0]["result"] == "linked"


def test_windows_are_equal_and_bounded() -> None:
    t = datetime(2026, 10, 5, 12, tzinfo=UTC)
    (b0, b1), (a0, a1) = postmerge.windows(t, t + timedelta(minutes=5))
    assert b1 == a0 == t and a1 - a0 == timedelta(minutes=15) == b1 - b0
    (b0, _), (_, a1) = postmerge.windows(t, t + timedelta(days=3))
    assert a1 - t == timedelta(hours=24) and t - b0 == timedelta(hours=24)


class D17:
    def __init__(self, action: str) -> None:
        self.action = action

    async def decide(self, decision_id: str, cs: Any, **kw: Any) -> Any:
        assert decision_id == "D17"
        return SimpleNamespace(p=0.9, band=Band.ACT, action=self.action, ledger_id="d17")


def watching(tmp_path: Path) -> RunState:
    s = run_state()
    s.pr = PRInfo(
        url="https://github.com/o/r/pull/3",
        number=3,
        branch="debugassist/x",
        base="release/1.6.1",
        draft=False,
        mode="live",
    )
    s.watch = Watch(pr_url=s.pr.url, pr_number=3, started_at="2026-10-05T10:00:00+00:00")
    assert s.triage
    s.triage.jira_key = deps(tmp_path).jira.create("[P1] crash", [("para", "x")], "P1", ["l"]).key
    return s


async def test_watch_waits_for_merge_deploy_and_traffic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = watching(tmp_path)
    d = deps(tmp_path, engine=D17("close_issue"), github=SimpleNamespace(merged=lambda repo, n: False))  # pyright: ignore[reportUnknownLambdaType]
    assert (await postmerge.check(s, d)).reason == "PR not merged yet"
    d.github = SimpleNamespace(merged=lambda repo, n: None)  # pyright: ignore[reportUnknownLambdaType]
    monkeypatch.setattr(postmerge, "_deploy_after", lambda repo, after: None)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    assert "not deployed" in str((await postmerge.check(s, d)).reason)
    deploy = {
        "repo": "miniride-client",
        "ref": "debugassist/x",
        "sha": "abc",
        "at": datetime.now(UTC).isoformat(),
    }
    monkeypatch.setattr(postmerge, "_deploy_after", lambda repo, after: deploy)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    monkeypatch.setattr(
        postmerge, "measure", lambda deps, state, a, b: {"sessions": 5, "affected_sessions": 0, "rate": 0.0}
    )  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    w = await postmerge.check(s, d)
    assert w.status == "watching" and "5 of 20 sessions" in str(w.reason)


async def test_resolved_issue_is_closed_everywhere_and_flag_restore_waits_for_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from debugassist.mcp_servers import feature_flags as ff

    s = watching(tmp_path)
    assert s.mitigation
    s.mitigation.flag, s.mitigation.action, s.mitigation.rolled_back_from = (
        "notif_router_v2",
        "rolled_back",
        5,
    )
    d = deps(tmp_path, engine=D17("close_issue"), github=SimpleNamespace(merged=lambda repo, n: True))  # pyright: ignore[reportUnknownLambdaType]
    deploy = {
        "repo": "miniride-client",
        "ref": "debugassist/x",
        "sha": "abc",
        "at": datetime.now(UTC).isoformat(),
    }
    monkeypatch.setattr(postmerge, "_deploy_after", lambda repo, after: deploy)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    rates = iter(
        [
            {"sessions": 200, "affected_sessions": 9, "rate": 0.045},
            {"sessions": 180, "affected_sessions": 0, "rate": 0.0},
        ]
    )
    monkeypatch.setattr(postmerge, "measure", lambda deps, state, a, b: next(rates))  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    posted: list[str] = []
    monkeypatch.setattr(
        postmerge.httpx,
        "post",
        lambda url, json=None, timeout=0: (
            posted.append(url) or SimpleNamespace(raise_for_status=lambda: None)
        ),
    )  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    restores: list[dict[str, Any]] = []

    def fake_restore(flag: str, pct: int, reason: str = "", dry_run: bool = True) -> dict[str, Any]:
        restores.append({"flag": flag, "pct": pct, "dry_run": dry_run})
        return {"applied": not dry_run}

    monkeypatch.setattr(ff, "rollback_flag", fake_restore)
    w = await postmerge.check(s, d)
    assert w.status == "resolved" and w.decision["action"] == "close_issue"
    assert posted == ["http://vitals/api/issues/VIT-1001/resolve"]
    assert s.triage and d.jira.snapshot(s.triage.jira_key)["status"] == "Done"
    assert restores == [{"flag": "notif_router_v2", "pct": 5, "dry_run": True}]  # policy: approval
    assert any("flag notif_router_v2 → 5% (dry run)" in a for a in w.actions)
    assert d.chat.inbox()[0]["title"].startswith("Resolved:")


async def test_still_happening_reopens(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    s = watching(tmp_path)
    d = deps(tmp_path, engine=D17("reopen_issue"), github=SimpleNamespace(merged=lambda repo, n: True))  # pyright: ignore[reportUnknownLambdaType]
    deploy = {"repo": "miniride-client", "ref": "x", "sha": "abc", "at": datetime.now(UTC).isoformat()}
    monkeypatch.setattr(postmerge, "_deploy_after", lambda repo, after: deploy)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    monkeypatch.setattr(
        postmerge,
        "measure",
        lambda deps, state, a, b: {"sessions": 100, "affected_sessions": 4, "rate": 0.04},
    )  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    w = await postmerge.check(s, d)
    assert w.status == "reopened" and s.triage
    assert d.jira.snapshot(s.triage.jira_key)["status"] == "In Progress"
    assert d.chat.inbox()[0]["level"] == "alert"


def test_a_jira_outage_does_not_stop_the_resolution(tmp_path: Path) -> None:
    import httpx

    def boom(*_a: Any, **_k: Any) -> None:
        raise httpx.ConnectError("down")

    d = deps(tmp_path)
    d.jira = SimpleNamespace(comment=boom, transition=boom)
    assert postmerge._jira(d, "SCRUM-9", "x", "Done") == "jira SCRUM-9: failed (ConnectError)"
