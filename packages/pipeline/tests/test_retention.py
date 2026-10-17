"""ROADMAP-100 057: old runs lose their worktree, keep their record; watched runs keep everything."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from debugassist.pipeline import retention


def _run(runs: Path, run_id: str, status: str = "done") -> Path:
    d = runs / run_id
    (d / "repo" / "node_modules").mkdir(parents=True)
    (d / "repo" / "node_modules" / "big.js").write_text("x" * 1000)
    (d / "nodes").mkdir()
    (d / "state.json").write_text(json.dumps({"status": status}))
    return d


def test_prune_removes_old_worktrees_only(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    old, watched, recent = (
        _run(runs, "20261001-120000-vit-1"),
        _run(runs, "20261001-130000-vit-2", status="watching"),
        _run(runs, "20261016-120000-vit-3"),
    )
    (runs / "not-a-run").mkdir()
    items = retention.prunable(14, runs, now=datetime(2026, 10, 17, tzinfo=UTC))
    assert [i.run for i in items] == [old] and items[0].bytes == 1000
    retention.prune(items, targets=tmp_path / "no-targets")
    assert not (old / "repo").exists() and (old / "state.json").exists() and (old / "nodes").exists()
    assert (watched / "repo").exists() and (recent / "repo").exists()


def test_audit_rows_filter_by_run_and_action(tmp_path: Path) -> None:
    """ROADMAP-100 066."""
    from debugassist.core.policy import read_audit

    log = tmp_path / "audit.jsonl"
    entries = [
        {"run_id": "r1", "action": "github.open_pr", "verdict": "live", "result": {"applied": True}},
        {"run_id": "r1", "action": "jira.comment", "verdict": "deny", "result": {"applied": False}},
        {"run_id": "r2", "action": "github.comment", "verdict": "live"},
    ]
    log.write_text("\n".join(json.dumps(e) for e in entries) + "\n{cut off")
    assert [e.action for e in read_audit(log, run="r1")] == ["github.open_pr", "jira.comment"]
    assert [e.run_id for e in read_audit(log, action="github.")] == ["r1", "r2"]
    assert [e.applied for e in read_audit(log)] == [True, False, None]
    assert len(read_audit(log, last=1)) == 1 and read_audit(tmp_path / "none.jsonl") == []


def test_the_health_verdict_names_what_went_off_design() -> None:
    """ROADMAP-100 059."""
    from debugassist.pipeline.cli import health_verdict
    from debugassist.pipeline.state import RunState

    s = RunState(run_id="r", issue_ref="x")
    assert health_verdict(s, 0, 0) == "healthy"
    s.errors = ["classify_rca: run budget exhausted ($0.5000 of $0.50)", ""]
    assert health_verdict(s, 2, 1) == (
        "⚠ 2 decision(s) fell back · 1 agent(s) stopped by budget · 1 write(s) denied by policy"
    )


def test_a_run_budget_is_the_lowest_of_agent_type_repository_and_global_cap(monkeypatch: Any) -> None:
    """ROADMAP-100 075."""
    from types import SimpleNamespace

    from debugassist.pipeline import budget
    from debugassist.pipeline.state import RunState

    deps: Any = SimpleNamespace(agent_type={"run_budget_usd": 3.0})
    s = RunState.model_validate(
        json.loads((Path(__file__).parent / "fixtures" / "run_state.json").read_text())
    )
    assert s.issue
    assert budget.limit(deps, s) == 3.0
    s.issue.run_budget_usd = 0.75  # the repository's pipeline.yaml says so
    assert budget.limit(deps, s) == 0.75
    monkeypatch.setenv("DA_RUN_BUDGET_CAP_USD", "0.5")
    assert budget.limit(deps, s) == 0.5
    monkeypatch.delenv("DA_RUN_BUDGET_CAP_USD")
    assert budget.limit(SimpleNamespace(agent_type={"run_budget_usd": 50.0}), None) == budget.HARD_CAP_USD  # pyright: ignore[reportArgumentType]
