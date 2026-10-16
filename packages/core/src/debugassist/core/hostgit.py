"""Host-side git for directories an agent may have written.

A run's worktree is mounted read-write into the sandbox, so everything in it is untrusted — `.git` included.
Plain `git` run with the worktree as cwd discovers its repository from `<worktree>/.git` and honours that
repository's config, so an agent that swaps `.git` for a directory whose config sets `core.fsmonitor` (or
hooks, filters, an external diff) gets a command run on the host. Host code therefore never lets git discover
the repository from a run directory: `run()` resolves the git dir itself and passes it explicitly, and only
accepts a worktree's `.git` file when the main repository's own record of that worktree points back at it.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from debugassist.core.policy import ROOT

RUNS = ROOT / ".data" / "runs"
# Neutralise the config-driven ways git runs programs, even for a git dir we trust.
HARDEN = ("-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null")
# Variables that would redirect git to another repository than the one resolved here.
_REDIRECT = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY")


class UntrustedGitDir(RuntimeError):
    pass


def _strict(path: Path) -> bool:
    """Run directories are written by agents: there, refuse anything but a verified linked worktree."""
    p = path.resolve()
    return p == RUNS.resolve() or RUNS.resolve() in p.parents


def trusted_gitdir(worktree: Path) -> Path | None:
    """The git dir for `worktree`, or None when it cannot be established without trusting the worktree.

    A linked worktree's `.git` is a file naming its admin dir (`<repo>/.git/worktrees/<name>`); that admin dir
    holds a `gitdir` file pointing back at `<worktree>/.git`. The admin dir lives outside the worktree, where
    the agent cannot write, so the back-pointer is the trusted half of the pair.
    """
    wt = worktree.resolve()
    dot = worktree / ".git"
    if dot.is_symlink():
        return None
    if dot.is_dir():
        return None if _strict(worktree) else dot.resolve()
    if not dot.is_file():
        return None
    m = re.match(r"gitdir:\s*(.+)", dot.read_text(errors="replace").strip())
    if not m:
        return None
    admin = Path(m.group(1).strip())
    admin = (admin if admin.is_absolute() else worktree / admin).resolve()
    if admin == wt or wt in admin.parents:
        return None
    try:
        back = Path((admin / "gitdir").read_text().strip())
    except OSError:
        return None
    back = (back if back.is_absolute() else admin / back).resolve()
    return admin if back == wt / ".git" else None


def argv(cwd: Path, *args: str) -> list[str]:
    gitdir = trusted_gitdir(cwd)
    if gitdir is not None:
        return ["git", f"--git-dir={gitdir}", f"--work-tree={cwd.resolve()}", *HARDEN, *args]
    if _strict(cwd):
        raise UntrustedGitDir(f"refusing to run git in {cwd}: its .git is not the worktree's own")
    return ["git", *HARDEN, *args]  # a directory no agent writes (the main checkout, a test repo)


def env(extra: dict[str, str] | None = None) -> dict[str, str]:
    out = {k: v for k, v in os.environ.items() if k not in _REDIRECT}
    out["GIT_CONFIG_NOSYSTEM"] = "1"
    return out | (extra or {})


def run(
    cwd: Path,
    *args: str,
    input: str | None = None,
    check: bool = False,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """`git <args>` for the repository at `cwd`, never trusting configuration the agent could have written."""
    return subprocess.run(  # noqa: S603 - argv is git plus fixed hardening flags
        argv(Path(cwd), *args),
        cwd=cwd,
        input=input,
        capture_output=True,
        text=True,
        check=check,
        env=env(extra_env),
    )
