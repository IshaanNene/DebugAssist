"""Host git never takes its repository or config from a directory the sandboxed agent writes (audit P1-1)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from debugassist.core import hostgit


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def worktree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A main repo outside the run directory and a linked worktree inside it, as `Sandbox.create` makes."""
    runs = tmp_path / "runs"
    monkeypatch.setattr(hostgit, "RUNS", runs)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "a.txt").write_text("one\n")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    wt = runs / "r1" / "repo"
    wt.parent.mkdir(parents=True)
    _git(repo, "worktree", "add", "-q", "-b", "debugassist/x", str(wt))
    return wt


def _hostile_gitdir(path: Path, marker: Path) -> None:
    """A repository whose config runs a command whenever git reads the index."""
    path.mkdir()
    _git(path, "init", "-q")
    with (path / ".git" / "config").open("a") as f:
        f.write(f'[core]\n\tfsmonitor = "touch {marker}; false"\n')


def test_a_real_worktree_works(worktree: Path) -> None:
    (worktree / "a.txt").write_text("two\n")
    assert "+two" in hostgit.run(worktree, "diff", check=True).stdout
    assert hostgit.trusted_gitdir(worktree) is not None


def test_a_swapped_dot_git_directory_is_refused(worktree: Path, tmp_path: Path) -> None:
    marker = tmp_path / "pwned"
    (worktree / ".git").unlink()
    _hostile_gitdir(tmp_path / "evil", marker)
    (tmp_path / "evil" / ".git").rename(worktree / ".git")
    with pytest.raises(hostgit.UntrustedGitDir):
        hostgit.run(worktree, "status")
    assert not marker.exists()


def test_a_dot_git_file_pointing_into_the_worktree_is_refused(worktree: Path, tmp_path: Path) -> None:
    marker = tmp_path / "pwned"
    _hostile_gitdir(worktree / "fake", marker)
    admin = worktree / "fake" / ".git"
    (admin / "gitdir").write_text(str(worktree / ".git") + "\n")  # forge the back-pointer too
    (worktree / ".git").write_text(f"gitdir: {admin}\n")
    with pytest.raises(hostgit.UntrustedGitDir):
        hostgit.run(worktree, "status")
    assert not marker.exists()


def test_a_dot_git_file_pointing_at_another_worktree_is_refused(worktree: Path, tmp_path: Path) -> None:
    other = tmp_path / "other"
    _git(tmp_path / "repo", "worktree", "add", "-q", "-b", "other", str(other))
    (worktree / ".git").write_text((other / ".git").read_text())
    with pytest.raises(hostgit.UntrustedGitDir):
        hostgit.run(worktree, "status")


def test_fsmonitor_is_off_even_outside_run_directories(tmp_path: Path) -> None:
    marker = tmp_path / "pwned"
    _hostile_gitdir(tmp_path / "plain", marker)
    (tmp_path / "plain" / "f").write_text("x")
    hostgit.run(tmp_path / "plain", "status")
    assert not marker.exists()


def test_sandbox_containers_run_least_privileged_with_a_read_only_git(
    worktree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from debugassist.integrations import sandbox

    argv: list[str] = []

    def fake_run(cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        argv.extend(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(sandbox.Sandbox, "worktree", property(lambda self: worktree))  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    monkeypatch.setattr(sandbox.subprocess, "run", fake_run)
    sandbox.Sandbox("r1", worktree, "o/r", "python").run("pytest -q")
    joined = " ".join(argv)
    for flag in (
        "--cap-drop ALL",
        "--security-opt no-new-privileges",
        "--pids-limit",
        "--network none",
        "--user",
    ):
        assert flag in joined
    assert f"{worktree / '.git'}:/work/.git:ro" in argv
