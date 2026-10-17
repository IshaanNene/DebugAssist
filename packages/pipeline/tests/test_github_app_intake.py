"""GitHub App intake and poll, on the mock app with a local git repository standing in for GitHub."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from debugassist.core.policy import Policy, PolicyGate
from debugassist.integrations.github_app import GitHubAppMock
from debugassist.pipeline import app_cli, app_intake
from debugassist.pipeline.nodes import app_comment
from debugassist.pipeline.state import RunState

CONFIG = "version: 1\ncomponents:\n  .:\n    path: .\n    language: python\n    test: pytest -q\n"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True, capture_output=True
    )


def _upstream(tmp: Path, onboarded: bool = True) -> Path:
    up = tmp / "upstream"
    up.mkdir()
    _git(up, "init", "-q", "-b", "main")
    (up / "lib.py").write_text("def half(x):\n    return x // 2\n")
    if onboarded:
        (up / ".DebugAssist").mkdir()
        (up / ".DebugAssist" / "pipeline.yaml").write_text(CONFIG)
    _git(up, "add", ".")
    _git(up, "commit", "-qm", "init")
    return up


def _app(tmp: Path, up: Path, issues: list[dict[str, Any]] | None = None) -> GitHubAppMock:
    a = GitHubAppMock(tmp / "mock")
    a.state_file.write_text(json.dumps({"repos": {"acme/widgets": {
        "clone_url": str(up), "default_branch": "main", "description": "a widget library",
        "issues": issues if issues is not None else [
            {"number": 3, "title": "half(3) is 1", "body": "```python\nhalf(3)\n```", "html_url": "https://x/3",
             "created_at": "2026-10-16T00:00:00Z", "labels": [{"name": "debugassist"}]},
            {"number": 4, "title": "unrelated", "labels": [{"name": "question"}]},
        ],
    }}}))  # fmt: skip
    return a


@pytest.fixture(autouse=True)
def _paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_intake, "TARGETS", tmp_path / "targets")
    monkeypatch.setattr(app_cli, "QUEUE", tmp_path / "queue")
    monkeypatch.setattr(app_cli, "SEEN", tmp_path / "seen.json")


def test_ref_parsing() -> None:
    assert app_intake.parse_ref("GHA:acme/widgets#12") == ("acme/widgets", 12)
    assert app_intake.ref("acme/widgets", 12) == "GHA:acme/widgets#12"
    with pytest.raises(ValueError):
        app_intake.parse_ref("GH-cachetools-435")


def test_ingest_checks_out_the_default_branch_and_builds_the_issue(tmp_path: Path) -> None:
    a = _app(tmp_path, _upstream(tmp_path))
    issue = app_intake.ingest("GHA:acme/widgets#3", a)
    dest = tmp_path / "targets" / "gh--acme--widgets"
    sha = subprocess.run(
        ["git", "rev-parse", "--short=10", "HEAD"], cwd=dest, capture_output=True, text=True
    ).stdout.strip()
    assert issue.repo == "gh--acme--widgets" and issue.gh_repo == "acme/widgets"
    assert issue.last_version == f"app-{sha}" and issue.base_branch == "main" and issue.app_issue == 3
    assert issue.language == "python" and issue.report["body"].startswith("```python")
    tags = subprocess.run(["git", "tag"], cwd=dest, capture_output=True, text=True).stdout.split()
    assert f"vapp-{sha}" in tags  # the release the sandbox branches from
    assert issue.about and "a widget library" in issue.about


def test_a_repo_without_a_pipeline_config_gets_one_comment_and_no_run(tmp_path: Path) -> None:
    a = _app(tmp_path, _upstream(tmp_path, onboarded=False))
    with pytest.raises(app_intake.NotOnboarded):
        app_intake.ensure_checkout(a, "acme/widgets")
    assert app_cli.run_one(a, "acme/widgets", 3) == 0
    assert app_cli.run_one(a, "acme/widgets", 3) == 0  # again: still one comment
    [c] = a.comments("acme/widgets", 3)
    assert c.startswith(app_cli.NOT_ONBOARDED) and ".DebugAssist/pipeline.yaml" in c


def test_pending_takes_webhook_deliveries_and_labeled_issues_once(tmp_path: Path) -> None:
    a = _app(tmp_path, _upstream(tmp_path))
    gate = PolicyGate(
        Policy.model_validate({"repos": [], "app_installations": True}), installed=a.installed_repos
    )
    (tmp_path / "queue").mkdir()
    (tmp_path / "queue" / "d1.json").write_text(json.dumps({"repo": "acme/widgets", "number": 9}))
    assert app_cli.pending(a, gate, "debugassist") == [
        ("acme/widgets", 9, "webhook"),
        ("acme/widgets", 3, "labeled"),
    ]
    assert not list((tmp_path / "queue").glob("*.json"))  # taken: held in processing/ until the run ends
    app_cli.done_delivery("acme/widgets", 9)
    a.comment("acme/widgets", 3, "<!-- debugassist:run r1 -->\ndone")
    assert app_cli.pending(a, gate, "debugassist") == []  # already answered
    closed = PolicyGate(
        Policy.model_validate({"repos": [], "app_installations": False}), installed=a.installed_repos
    )
    a2 = _app(tmp_path / "b", _upstream_mk(tmp_path / "b"))
    assert app_cli.pending(a2, closed, "debugassist") == []  # the policy does not allow the repo


def _upstream_mk(p: Path) -> Path:
    p.mkdir(parents=True)
    return _upstream(p)


def test_the_comment_carries_the_marker_the_cause_and_the_pr() -> None:
    fx = json.loads((Path(__file__).parent / "fixtures" / "run_state.json").read_text())
    state = RunState.model_validate(fx)
    text = app_comment(state, "https://github.com/acme/widgets/pull/5", "draft_pr")
    assert text.startswith("<!-- debugassist:run ") and "pull/5" in text
    assert state.rca and state.rca.output and state.rca.output.location.file in text
    assert "outside this repository" in app_comment(state, None, "rca_only")


def test_a_failed_run_is_retried_with_backoff_then_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Audit P2-12: a failed run was marked `exit N` and never retried or reported."""
    a = _app(tmp_path, _upstream(tmp_path))
    gate = PolicyGate(
        Policy.model_validate({"repos": [], "app_installations": True}), installed=a.installed_repos
    )
    monkeypatch.setattr(app_cli, "_spawn", lambda ref, llm: 2)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    clock = [1_000_000.0]
    monkeypatch.setattr(app_cli.time, "time", lambda: clock[0])
    for attempt in range(1, app_cli.MAX_ATTEMPTS + 1):
        assert app_cli.pending(a, gate, "debugassist") == [("acme/widgets", 3, "labeled")]
        assert app_cli.run_one(a, "acme/widgets", 3) == 2
        assert app_cli.pending(a, gate, "debugassist") == []  # backing off
        clock[0] += app_cli.RETRY_BASE * 2**attempt
    [c] = a.comments("acme/widgets", 3)
    assert c.startswith(app_cli.FAILED)
    assert app_cli.pending(a, gate, "debugassist") == []  # reported: not run again


def test_a_webhook_delivery_survives_until_its_run_ends(tmp_path: Path) -> None:
    a = _app(tmp_path, _upstream(tmp_path))
    gate = PolicyGate(
        Policy.model_validate({"repos": [], "app_installations": True}), installed=a.installed_repos
    )
    (tmp_path / "queue").mkdir()
    (tmp_path / "queue" / "d1.json").write_text(json.dumps({"repo": "acme/widgets", "number": 9}))
    assert ("acme/widgets", 9, "webhook") in app_cli.pending(a, gate, "debugassist")
    # the poller dies here: the delivery is still there for the next pass
    assert ("acme/widgets", 9, "webhook") in app_cli.pending(a, gate, "debugassist")
    app_cli.done_delivery("acme/widgets", 9)
    assert ("acme/widgets", 9, "webhook") not in app_cli.pending(a, gate, "debugassist")


def test_only_one_poller_runs_at_a_time(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Roadmap 069: two pollers would run every labeled issue twice."""
    monkeypatch.setattr(app_cli, "LOCK", tmp_path / "poll.lock")
    first = app_cli.poll_lock()
    assert first is not None and app_cli.poll_lock() is None
    first.close()
    again = app_cli.poll_lock()
    assert again is not None
    again.close()
