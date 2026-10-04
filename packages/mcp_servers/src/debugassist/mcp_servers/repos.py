"""Repository roots the code-search and git-history servers may read (name → path).

CODE_REPOS='{"miniride-client": "/path/to/worktree", …}' points at the run's sandbox worktrees; the
default is the MiniRide submodules for interactive use.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from debugassist.core.policy import ROOT


def repo_roots() -> dict[str, Path]:
    raw = os.environ.get("CODE_REPOS")
    if raw:
        return {k: Path(v) for k, v in json.loads(raw).items()}
    return {p.name: p for p in sorted((ROOT / "targets").glob("miniride-*")) if (p / ".git").exists()}


def resolve(repo: str) -> Path:
    roots = repo_roots()
    if repo not in roots:
        raise ValueError(f"unknown repo {repo!r}; available: {sorted(roots)}")
    return roots[repo]
