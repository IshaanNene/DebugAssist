"""Workspace (ROADMAP-100 036): git, reads, writes and walks on a run's worktree, all through the guards."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from debugassist.core.guards import GuardError
from debugassist.core.workspace import Workspace


def _repo(tmp_path: Path) -> Workspace:
    root = tmp_path / "wt"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    (root / "a.py").write_text("x = 1\n")
    (root / "keep.py").write_text("y = 2\n")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"], cwd=root, check=True
    )
    subprocess.run(["git", "tag", "v1"], cwd=root, check=True)
    return Workspace(root)


def test_git_status_show_reset_and_apply(tmp_path: Path) -> None:
    ws = _repo(tmp_path)
    assert ws.branch() == "main" and ws.has_ref("v1") and not ws.has_ref("v9")
    ws.write("a.py", "x = 2\n")
    ws.write("tests/test_new.py", "assert True\n")
    ws.git("mv", "keep.py", "kept.py", check=True)
    assert set(ws.status()) == {"a.py", "tests/test_new.py", "kept.py", "keep.py"}  # both sides of the rename
    assert ws.dirty()
    assert ws.show("v1", "a.py") == "x = 1\n" and ws.show("v1", "missing.py") is None
    diff = ws.git("diff", "v1", "--", "a.py", check=True).stdout
    ws.reset("v1")
    assert not ws.dirty() and ws.read("a.py") == "x = 1\n" and not ws.is_file("tests/test_new.py")
    ws.apply(diff)
    assert ws.read("a.py") == "x = 2\n"


def test_paths_stay_inside_the_worktree(tmp_path: Path) -> None:
    ws = _repo(tmp_path)
    (tmp_path / "secret.txt").write_text("outside")
    (ws.root / "link.txt").symlink_to(tmp_path / "secret.txt")  # an agent-planted link out
    (ws.root / "inner.txt").symlink_to(ws.root / "a.py")  # a link that stays inside
    for rel in ("../secret.txt", "link.txt", ".git/config", ".env"):
        with pytest.raises(GuardError):
            ws.read(rel)
        assert not ws.is_file(rel)  # queries treat a refused path as absent
    with pytest.raises(GuardError):
        ws.write("../escape.txt", "no")
    assert not (tmp_path / "escape.txt").exists()
    assert ws.is_symlink("link.txt") and ws.read("inner.txt") == "x = 1\n"
    ws.remove("link.txt")  # the planted link goes; what it points at is never touched
    assert not ws.is_symlink("link.txt") and (tmp_path / "secret.txt").read_text() == "outside"
    ws.remove("../secret.txt")  # a path outside is refused quietly
    assert (tmp_path / "secret.txt").exists()


def test_walks_and_globs_never_follow_or_return_symlinks(tmp_path: Path) -> None:
    ws = _repo(tmp_path)
    ws.write("e2e/a.spec.ts", "test()\n")
    (ws.root / "e2e" / "b.spec.ts").symlink_to(ws.root / "a.py")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "x.py").write_text("")
    (ws.root / "dirlink").symlink_to(outside, target_is_directory=True)
    walked = {str(p.relative_to(ws.root)) for p in ws.walk()}
    assert walked == {"a.py", "keep.py", "e2e/a.spec.ts"}
    assert ws.glob("e2e", "*.spec.ts") == ["e2e/a.spec.ts"]
    assert ws.glob("../outside", "*.py") == [] and ws.walk("dirlink") == []
