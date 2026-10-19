"""The pipeline reaches a run's worktree only through `core.workspace.Workspace` (ROADMAP-100 036): no git call
of its own, no path built by joining onto the worktree, no walk around the guards."""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).parents[1] / "src" / "debugassist" / "pipeline"

# Host checkouts that are not run worktrees: an installed repository's clone, the targets' own repos.
HOST_GIT = {"app_intake.py", "retention.py"}
DIRECT = re.compile(r"\bhostgit\b|\bwalk_files\b|worktree / |worktree\) / ")


def test_no_module_touches_a_worktree_around_the_workspace() -> None:
    found: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        rel = str(path.relative_to(SRC))
        for n, line in enumerate(path.read_text().splitlines(), 1):
            code = line.split("#", 1)[0]
            if rel in HOST_GIT and "hostgit" in code:
                continue
            if 'f"cd {' in code:  # a command line shown to a person, not an access
                continue
            if DIRECT.search(code):
                found.append(f"{rel}:{n}: {line.strip()}")
    assert not found, "use sb.workspace / Workspace(worktree):\n" + "\n".join(found)
