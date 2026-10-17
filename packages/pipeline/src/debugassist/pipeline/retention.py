"""Run retention (ROADMAP-100 057): old runs keep their record, not their worktree.

A run directory holds `state.json`, `nodes/` and `agents/` (the record: the dashboard, reports and cassette
replays read them) and `repo/`, the sandbox worktree with its dependencies (hundreds of MB, needed only while the
run, a resume or the diff fixer works on it). Pruning removes `repo/` from runs older than a cutoff that are not
still being watched after a merge, then lets git forget the worktrees.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from debugassist.core import hostgit
from debugassist.core.policy import ROOT

RUNS = ROOT / ".data" / "runs"
TARGETS = ROOT / "targets"


@dataclass(frozen=True)
class Prunable:
    run: Path
    bytes: int


def _started(run_id: str) -> datetime | None:
    try:
        return datetime.strptime(run_id[:15], "%Y%m%d-%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def _size(path: Path) -> int:
    return sum(f.lstat().st_size for f in path.rglob("*") if not f.is_symlink() and f.is_file())


def prunable(older_than_days: int, runs: Path = RUNS, now: datetime | None = None) -> list[Prunable]:
    cutoff = (now or datetime.now(UTC)) - timedelta(days=older_than_days)
    out: list[Prunable] = []
    for run in sorted(p for p in runs.iterdir() if p.is_dir()) if runs.is_dir() else []:
        started = _started(run.name)
        repo = run / "repo"
        if started is None or started >= cutoff or not repo.exists():
            continue
        try:
            status = json.loads((run / "state.json").read_text()).get("status")
        except (OSError, json.JSONDecodeError):
            status = None
        if status == "watching":  # `debugassist watch` may still need it after the deploy
            continue
        out.append(Prunable(run, _size(repo)))
    return out


def prune(items: list[Prunable], targets: Path = TARGETS) -> None:
    for item in items:
        shutil.rmtree(item.run / "repo", ignore_errors=True)
    for repo in sorted(targets.iterdir()) if targets.is_dir() else []:
        if (repo / ".git").exists():
            hostgit.run(repo, "worktree", "prune")  # drop the registrations of the deleted worktrees
