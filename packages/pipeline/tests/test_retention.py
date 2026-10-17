"""ROADMAP-100 057: old runs lose their worktree, keep their record; watched runs keep everything."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

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
