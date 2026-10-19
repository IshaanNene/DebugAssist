"""Install cache (ROADMAP-100 048): one install per (image, command, manifests), copied into later runs."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from debugassist.integrations import installcache
from debugassist.integrations.sandbox import CommandResult, Sandbox


class InstallSandbox(Sandbox):
    """`run` stands in for the install container: it writes node_modules (with an inner symlink, as pnpm does)
    and counts how often it ran."""

    installs: int = 0

    @property
    def run_worktree(self) -> Path:
        return self.repo_path.parent / f"wt-{self.run_id}"

    def ensure_image(self, image: str) -> CommandResult | None:
        return None

    def run(
        self, command: str, *, workdir: str = ".", network: bool = False, timeout: int = 600
    ) -> CommandResult:
        type(self).installs += 1
        mods = self.worktree / "node_modules"
        (mods / ".pnpm" / "left-pad@1").mkdir(parents=True)
        (mods / ".pnpm" / "left-pad@1" / "index.js").write_text("module.exports = 1\n")
        (mods / "left-pad").symlink_to(".pnpm/left-pad@1")
        (self.worktree / "test-results").mkdir()  # run output, never cached
        return CommandResult(command, 0, "installed")


def _result(code: int, output: str) -> object:
    def run(command: str, **_: object) -> CommandResult:
        return CommandResult(command, code, output)

    return run


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(installcache, "CACHE", tmp_path / "cache")
    monkeypatch.delenv("DA_INSTALL_CACHE", raising=False)
    InstallSandbox.installs = 0
    src = tmp_path / "src"
    src.mkdir()
    _git(src, "init", "-q", "-b", "main")
    (src / "package.json").write_text('{"name": "x"}\n')
    (src / "pnpm-lock.yaml").write_text("lockfileVersion: 9\n")
    (src / "index.ts").write_text("export const a = 1\n")
    (src / ".gitignore").write_text("node_modules/\ntest-results/\n")
    _git(src, "add", ".")
    _git(src, "commit", "-qm", "init")
    return src


def _sandbox(repo: Path, run_id: str) -> InstallSandbox:
    sb = InstallSandbox(run_id, repo, "o/x")
    sb.create("main", f"b-{run_id}")
    return sb


def test_the_second_run_copies_instead_of_installing(repo: Path) -> None:
    first = _sandbox(repo, "a")
    assert first.install("pnpm install").output == "installed"
    second = _sandbox(repo, "b")
    res = second.install("pnpm install")
    assert InstallSandbox.installs == 1 and res.exit_code == 0 and "cache hit" in res.output
    assert (second.worktree / "node_modules" / "left-pad").is_symlink()  # links kept as links
    assert (second.worktree / "node_modules" / "left-pad" / "index.js").read_text() == "module.exports = 1\n"
    assert not (second.worktree / "test-results").exists()
    # The run writes to its copy; the cache, and the next run, are unchanged.
    (second.worktree / "node_modules" / ".pnpm" / "left-pad@1" / "index.js").write_text("poisoned\n")
    third = _sandbox(repo, "c")
    third.install("pnpm install")
    assert (third.worktree / "node_modules" / "left-pad" / "index.js").read_text() == "module.exports = 1\n"
    assert InstallSandbox.installs == 1


def test_a_changed_lockfile_command_or_component_misses(repo: Path) -> None:
    _sandbox(repo, "a").install("pnpm install")
    _sandbox(repo, "b").install("pnpm install --prod")
    _sandbox(repo, "c").install("pnpm install", workdir="app")
    assert InstallSandbox.installs == 3
    (repo / "pnpm-lock.yaml").write_text("lockfileVersion: 9\n# left-pad@2\n")
    _git(repo, "commit", "-qam", "bump")
    _sandbox(repo, "d").install("pnpm install")
    assert InstallSandbox.installs == 4
    (repo / "index.ts").write_text("export const a = 2\n")  # source changes do not invalidate
    _git(repo, "commit", "-qam", "src")
    _sandbox(repo, "e").install("pnpm install")
    assert InstallSandbox.installs == 4


def test_a_worktree_that_already_has_dependencies_neither_uses_nor_fills_it(repo: Path) -> None:
    sb = _sandbox(repo, "a")
    (
        sb.worktree / "node_modules"
    ).mkdir()  # left by an earlier attempt, maybe touched by the agent's commands
    (sb.worktree / "node_modules" / "stale.js").write_text("")
    sb.run = _result(0, "installed")  # pyright: ignore[reportAttributeAccessIssue]
    sb.install("pnpm install")
    assert not installcache.CACHE.exists() or not any(installcache.CACHE.iterdir())


def test_off_switch_and_failed_installs_are_not_cached(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DA_INSTALL_CACHE", "0")
    _sandbox(repo, "a").install("pnpm install")
    _sandbox(repo, "b").install("pnpm install")
    assert InstallSandbox.installs == 2
    monkeypatch.delenv("DA_INSTALL_CACHE")
    failing = _sandbox(repo, "c")
    failing.run = _result(1, "ERR_PNPM")  # pyright: ignore[reportAttributeAccessIssue]
    assert failing.install("pnpm install").exit_code == 1
    assert (
        installcache.lookup(installcache.key(failing.workspace, "node:22-alpine", "pnpm install", ".") or "")
        is None
    )


def test_prune_keeps_the_most_recently_used(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    for i, k in enumerate(["old", "mid", "new"]):
        (root / k).mkdir(parents=True)
        (root / k / "manifest.json").write_text('{"dirs": []}')
        os.utime(root / k / "manifest.json", (1000 + i, 1000 + i))
    assert installcache.prune(keep=2, root=root) == ["old"]
    assert sorted(p.name for p in root.iterdir()) == ["mid", "new"]
