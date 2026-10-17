"""A sandbox working in another checkout (the release checks, P3-16) mounts the run worktree's dependencies —
never a directory reached through a symlink the agent planted, which would mount some other host path."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from debugassist.integrations import sandbox
from debugassist.integrations.sandbox import Sandbox


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True, capture_output=True
    )


def test_checkout_mounts_the_run_worktrees_dependency_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sandbox, "RUNS", tmp_path)
    sb = Sandbox("r1", tmp_path / "origin", "acme/toy", "typescript")
    wt = sb.run_worktree
    (wt / "gateway" / "node_modules" / "x").mkdir(parents=True)
    (wt / "gateway" / "node_modules" / "x" / "index.js").write_text("")
    (wt / ".gitignore").write_text("node_modules/\n.venv/\n")
    (wt / "src").mkdir()
    (wt / "src" / "a.ts").write_text("export {}\n")
    _git(wt, "init", "-q")
    _git(wt, "add", ".")
    _git(wt, "commit", "-qm", "init")
    secrets = tmp_path / "elsewhere"
    secrets.mkdir()
    (secrets / "id_rsa").write_text("")
    (wt / ".venv").symlink_to(secrets, target_is_directory=True)

    other = tmp_path / "checkout"
    other.mkdir()
    co = sb.checkout(other)
    assert co.worktree == other and co.run_worktree == wt and sb.worktree == wt
    assert co.shared == ("gateway/node_modules",)  # the symlinked .venv is not mounted
    assert co.mounts() == ["-v", f"{wt / 'gateway' / 'node_modules'}:/work/gateway/node_modules"]
    assert (other / "gateway" / "node_modules").is_dir()  # the mount point
    assert sb.mounts() == []
