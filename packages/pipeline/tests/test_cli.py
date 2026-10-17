# pyright: reportUnknownLambdaType=false
"""The pipeline's CLI: the run summary (with its health line), `audit`, `prune`, and the App's `status` / `poll`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from debugassist.core.policy import Policy, PolicyGate
from debugassist.pipeline import app_cli, cli
from debugassist.pipeline.state import RunState

FIXTURE = Path(__file__).parent / "fixtures" / "run_state.json"
runner = CliRunner()


def _app_of(*fns: Any) -> typer.Typer:
    t = typer.Typer()
    for fn in fns:
        t.command()(fn)
    return t


def test_the_summary_prints_every_section_and_the_health_line(capsys: pytest.CaptureFixture[str]) -> None:
    s = RunState.model_validate(json.loads(FIXTURE.read_text()))
    cli._summary(s)  # pyright: ignore[reportPrivateUsage]
    out = capsys.readouterr().out
    for label in ("  issue ", "  triage ", "  ship ", "  cost ", "  health "):
        assert label in out, label
    assert "health    healthy" in out or "health    ⚠" in out


def test_audit_lists_entries(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    gate = PolicyGate(Policy(actions={}), tmp_path / "audit.jsonl")
    gate.gated("jira.comment", lambda: None, run_id="r9", detail={})
    from debugassist.core import policy

    monkeypatch.setattr(policy, "DEFAULT_AUDIT", tmp_path / "audit.jsonl")
    out = runner.invoke(_app_of(cli.audit, cli.prune), ["audit", "--run", "r9"]).output
    assert "jira.comment" in out and "dry_run" in out and "not applied" in out


def test_prune_lists_then_deletes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from debugassist.pipeline import retention

    run = tmp_path / "runs" / "20261001-000000-x"
    (run / "repo").mkdir(parents=True)
    (run / "repo" / "f").write_text("x" * 10)
    (run / "state.json").write_text("{}")
    monkeypatch.setattr(retention, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(retention, "TARGETS", tmp_path / "targets")
    t = _app_of(cli.audit, cli.prune)
    assert "dry run" in runner.invoke(t, ["prune", "--older-than", "1"]).output and (run / "repo").exists()
    runner.invoke(t, ["prune", "--older-than", "1", "--apply"])
    assert not (run / "repo").exists() and (run / "state.json").exists()


def test_app_status_and_one_poll_pass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from debugassist.integrations.github_app import GitHubAppMock

    a = GitHubAppMock(tmp_path / "mock")
    a.state_file.write_text(json.dumps({"repos": {"acme/widgets": {"issues": []}}}))
    monkeypatch.setattr(app_cli, "_app", lambda: a)
    for name in ("QUEUE", "SEEN", "LOCK", "METRICS", "OUTCOMES"):
        monkeypatch.setattr(app_cli, name, tmp_path / name.lower())
    out = runner.invoke(app_cli.app, ["status"]).output
    assert "acme/widgets" in out
    result = runner.invoke(app_cli.app, ["poll", "--once", "--dry"])
    assert result.exit_code == 0, result.output


def test_decision_backends_and_fallbacks_come_from_the_ledger(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import sqlite3

    (tmp_path / ".data").mkdir()
    with sqlite3.connect(tmp_path / ".data" / "debugassist.db") as con:
        con.execute("create table decision_ledger (run_id text, backend text, fallback_reason text)")
        con.executemany(
            "insert into decision_ledger values (?, ?, ?)",
            [
                ("r1", "workers_ai", None),
                ("r1", "mock", "ClefTransientError: 503"),
                ("r1", "mock", "circuit open"),
            ],
        )
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    line = cli._decision_backends("r1")  # pyright: ignore[reportPrivateUsage]
    assert (
        line is not None
        and "2 mock" in line
        and "1 workers_ai" in line
        and "fell back: ClefTransientError" in line
    )
    assert cli._fallback_count("r1") == 2 and cli._fallback_count("r2") == 0  # pyright: ignore[reportPrivateUsage]
    assert cli._decision_backends("r2") is None  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(cli, "ROOT", tmp_path / "nowhere")
    assert cli._fallback_count("r1") == 0 and cli._decision_backends("r1") is None  # pyright: ignore[reportPrivateUsage]


def test_a_poll_pass_runs_queued_work_and_survives_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from debugassist.integrations.github import RateLimited
    from debugassist.integrations.github_app import GitHubAppMock

    a = GitHubAppMock(tmp_path / "mock")
    a.state_file.write_text(json.dumps({"repos": {"acme/widgets": {"issues": []}}}))
    monkeypatch.setattr(app_cli, "_app", lambda: a)
    for name in ("QUEUE", "SEEN", "LOCK", "METRICS", "OUTCOMES"):
        monkeypatch.setattr(app_cli, name, tmp_path / name.lower())
    app_cli.requeue("acme/widgets", 1)
    app_cli.requeue("acme/widgets", 2)
    ran: list[int] = []

    def run_one(a_: Any, repo: str, number: int, **_: Any) -> int:
        ran.append(number)
        if number == 2:
            raise RuntimeError("the app's API answered 502")
        return 0

    monkeypatch.setattr(app_cli, "run_one", run_one)
    result = runner.invoke(app_cli.app, ["poll", "--once"])
    assert result.exit_code == 0 and ran == [1, 2]  # an error on one issue does not stop the pass
    assert not list((tmp_path / "queue").rglob("*.json"))  # both deliveries finished
    metrics = json.loads((tmp_path / "metrics").read_text())
    assert metrics["errors"] == 1

    def limited(*_: Any) -> Any:
        raise RateLimited(30, "primary")

    monkeypatch.setattr(app_cli, "pending", limited)
    assert runner.invoke(app_cli.app, ["poll", "--once"]).exit_code == 0
    assert json.loads((tmp_path / "metrics").read_text())["rate_limited"] == 1
    assert "queued GHA:acme/widgets#7" in runner.invoke(app_cli.app, ["rerun", "GHA:acme/widgets#7"]).output


def test_the_github_router_sends_installed_repositories_through_the_app(tmp_path: Path) -> None:
    import subprocess
    from types import SimpleNamespace

    from debugassist.pipeline.deps import GitHubRouter

    calls: list[tuple[str, str]] = []

    def client(name: str) -> Any:
        return SimpleNamespace(
            remote_branch_exists=lambda repo, b: calls.append((name, "exists")) or True,
            push=lambda wt, b: calls.append((name, "push")),
            open_pr=lambda *a: calls.append((name, "pr")),
            comment=lambda *a: calls.append((name, "comment")),
            merged=lambda *a: calls.append((name, "merged")) or True,
        )

    app = SimpleNamespace(client=lambda repo: client("app") if repo == "acme/widgets" else None)
    r = GitHubRouter(client("token"), app)  # pyright: ignore[reportArgumentType]
    r.remote_branch_exists("acme/widgets", "main")
    r.open_pr("me/mine", "h", "b", "t", "body", True)
    r.comment("acme/widgets", 1, "x")
    r.merged("me/mine", 1)
    wt = tmp_path / "wt"
    wt.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=wt, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/acme/widgets.git"], cwd=wt, check=True
    )
    r.push(wt, "debugassist/x")
    assert calls == [
        ("app", "exists"),
        ("token", "pr"),
        ("app", "comment"),
        ("token", "merged"),
        ("app", "push"),
    ]


def test_a_failure_ratio_alert_goes_through_the_gate_at_most_hourly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ROADMAP-100 053."""
    from debugassist.core.policy import Verdict
    from debugassist.integrations.chat import ChatMock

    monkeypatch.setattr(app_cli, "METRICS", tmp_path / "metrics.json")
    monkeypatch.setattr(app_cli, "OUTCOMES", tmp_path / "outcomes.json")
    inbox = ChatMock(tmp_path / "inbox.jsonl")
    gate = PolicyGate(Policy(actions={"chat.message": Verdict.LIVE}), tmp_path / "audit.jsonl")
    clock = [1_000_000.0]
    monkeypatch.setattr(app_cli.time, "time", lambda: clock[0])
    outcomes = [0, 1, 1, 1, 1]  # 4 of 5 failed: more than half, and enough runs to judge
    assert [app_cli.record_outcome(c, gate, inbox) for c in outcomes] == [False, False, False, False, True]
    assert app_cli.record_outcome(1, gate, inbox) is False  # within the hour: no second page
    clock[0] += app_cli.ALERT_EVERY
    assert app_cli.record_outcome(1, gate, inbox) is True
    titles = sorted(m["title"] for m in inbox.inbox())
    assert titles == ["GitHub App: 4 of the last 5 runs failed", "GitHub App: 6 of the last 7 runs failed"]
    deny = PolicyGate(Policy(actions={"chat.message": Verdict.DENY}), tmp_path / "audit2.jsonl")
    clock[0] += app_cli.ALERT_EVERY
    app_cli.record_outcome(1, deny, inbox)
    assert len(inbox.inbox()) == 2  # denied by policy: nothing sent


def _comment_event(
    body: str, association: str = "MEMBER", pr: bool = True, user_type: str = "User"
) -> dict[str, Any]:
    return {
        "action": "created",
        "issue": {"number": 3, **({"pull_request": {"url": "u"}} if pr else {})},
        "comment": {
            "body": body,
            "author_association": association,
            "user": {"login": "maya", "type": user_type},
        },
        "repository": {"full_name": "acme/widgets"},
    }


@pytest.mark.parametrize(
    ("event", "ok"),
    [
        (_comment_event("@debugassist use the clamp helper"), True),
        (_comment_event("@DebugAssist: use the clamp helper", association="OWNER"), True),
        (
            _comment_event("@debugassist use the clamp helper", association="NONE"),
            False,
        ),  # a stranger: no credit
        (_comment_event("@debugassist use the clamp helper", user_type="Bot"), False),
        (_comment_event("@debugassist use the clamp helper", pr=False), False),  # an issue, not a PR
        (_comment_event("looks good"), False),
        (_comment_event("@debugassist"), False),  # nothing asked
    ],
)
def test_who_may_ask_for_a_revision(event: dict[str, Any], ok: bool) -> None:
    """ROADMAP-100 073."""
    r = app_cli.review_request(event)
    assert (r is not None) is ok
    if r is not None:
        assert (r.repo, r.pr, r.instruction, r.by) == ("acme/widgets", 3, "use the clamp helper", "maya")


def test_a_review_request_reaches_the_diff_fixer_of_the_run_that_opened_the_pr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runs = tmp_path / "runs"
    for rid, number in (("20261016-000000-a", 3), ("20261017-000000-b", 9)):
        (runs / rid).mkdir(parents=True)
        (runs / rid / "state.json").write_text(
            json.dumps({"pr": {"number": number}, "issue": {"gh_repo": "acme/widgets"}})
        )
    monkeypatch.setattr(app_cli, "RUNS_DIR", runs)
    assert (
        app_cli.run_for_pr("acme/widgets", 3) == "20261016-000000-a"
        and app_cli.run_for_pr("acme/x", 3) is None
    )
    fixes: list[tuple[str, str]] = []

    def spawn_fix(run_id: str, instruction: str) -> int:
        fixes.append((run_id, instruction))
        return 0

    monkeypatch.setattr(app_cli, "_spawn_fix", spawn_fix)
    for pr in (3, 4):
        r = app_cli.review_request(
            {
                **_comment_event("@debugassist use the clamp helper"),
                "issue": {"number": pr, "pull_request": {}},
            }
        )
        assert r is not None
        app_cli.REVIEWS.mkdir(parents=True, exist_ok=True)
        (app_cli.REVIEWS / f"r{pr}.json").write_text(r.model_dump_json())
    gate = PolicyGate(Policy(repos=["acme/widgets"]), tmp_path / "audit.jsonl")
    done = app_cli.review_pass(gate)
    assert fixes == [("20261016-000000-a", "use the clamp helper")]
    assert done == [
        "acme/widgets#3: revised by run 20261016-000000-a (exit 0)",
        "acme/widgets#4: no run of this app opened it",
    ]
    assert not list(app_cli.REVIEWS.glob("*.json"))


def test_a_pass_runs_repositories_in_parallel_and_each_repository_in_order() -> None:
    """ROADMAP-100 046."""
    import threading
    import time

    order: dict[str, list[int]] = {}
    active: set[str] = set()
    overlap: list[bool] = []
    lock = threading.Lock()

    def one(repo: str, number: int, why: str) -> None:
        with lock:
            overlap.append(bool(active - {repo}))
            active.add(repo)
            order.setdefault(repo, []).append(number)
        time.sleep(0.05)
        with lock:
            active.discard(repo)

    work = [("a/x", 1, "w"), ("b/y", 1, "w"), ("a/x", 2, "w"), ("b/y", 2, "w")]
    app_cli.run_work(work, one, workers=2)
    assert order == {"a/x": [1, 2], "b/y": [1, 2]} and any(overlap)
    order.clear()
    app_cli.run_work(work, one, workers=1)
    assert order == {"a/x": [1, 2], "b/y": [1, 2]}
