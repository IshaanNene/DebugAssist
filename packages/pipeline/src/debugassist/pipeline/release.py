"""Checks "on the release" in a disposable checkout, never by reverting the fix in the run's worktree.

Validation used to reverse-apply the source change in place (`git apply -R`), run the reproduction test and
re-apply it; a crash in between left the worktree without the fix, and a resumed validate after the fix was
committed found nothing to revert (audit P3-16). `release_checkout()` instead adds a detached worktree at the
release tag next to the run's worktree, copies the chosen paths into it as a patch (git reads them, so a
symlink the agent planted is copied as a link, not followed), and removes it afterwards — or on the next
check, after a crash. The run's worktree is never written.

It also classifies a fix's paths (audit P2-8): a change to a pre-existing test, the repository's harness or
test-runner config, its CI or a lockfile can make a suite pass without fixing anything, so the proof runs
without those changes and the PR is a flagged draft.
"""

from __future__ import annotations

import contextlib
import re
import shutil
import uuid
from collections.abc import Generator, Sequence
from pathlib import Path
from typing import Literal, Protocol

from debugassist.core import hostgit
from debugassist.integrations.sandbox import CommandResult
from debugassist.llm.workspace_tools import is_test_path

PREFIX = "release-check-"

PathClass = Literal["source", "new_test", "modified_test", "harness", "ci", "lockfile"]
# Changes that can make the proof pass without a fix: never part of the proof, always a flagged draft PR.
PROTECTED: tuple[PathClass, ...] = ("modified_test", "harness", "ci", "lockfile")
LOCKFILES = re.compile(
    r"(^|/)(pnpm-lock\.yaml|package-lock\.json|npm-shrinkwrap\.json|yarn\.lock|bun\.lockb?|uv\.lock|poetry\.lock|"
    r"Pipfile\.lock|go\.sum|Cargo\.lock|Gemfile\.lock|composer\.lock)$"
)
CI = re.compile(r"^(\.github/|\.gitlab-ci\.yml$|\.circleci/|\.buildkite/|Jenkinsfile$|azure-pipelines\.yml$)")
# The repository's own harness config and the files that decide which tests run and how.
HARNESS = re.compile(
    r"(^|/)(\.DebugAssist/|conftest\.py$|pytest\.ini$|tox\.ini$|noxfile\.py$|\.coveragerc$|"
    r"(vitest|jest|playwright|karma)\.config\.[cm]?[jt]s$|vitest\.workspace\.[cm]?[jt]s$|\.mocharc\.)"
)


class Checkout(Protocol):
    """What the checks need of a sandbox (the real one, or a test's local stand-in)."""

    @property
    def worktree(self) -> Path: ...

    def run(
        self, command: str, *, workdir: str = ".", network: bool = False, timeout: int = 600
    ) -> CommandResult: ...

    def diff(self, base: str = "HEAD") -> str: ...

    def checkout(self, root: Path) -> Checkout: ...


def _discard(worktree: Path, path: Path) -> None:
    hostgit.run(worktree, "worktree", "remove", "--force", str(path))
    shutil.rmtree(path, ignore_errors=True)
    hostgit.run(worktree, "worktree", "prune")


def discard_stale(worktree: Path) -> list[Path]:
    """Checkouts a crashed check left behind (next to the run's worktree)."""
    stale = sorted(worktree.parent.glob(f"{PREFIX}*"))
    for path in stale:
        _discard(worktree, path)
    return stale


def patch(worktree: Path, base: str, paths: Sequence[str]) -> str:
    """`paths` as they are in `worktree`, as a binary patch against `base` (new files included)."""
    if not paths:
        return ""
    hostgit.run(worktree, "add", "-A", "--intent-to-add", ".")  # new files show in the diff
    return hostgit.run(worktree, "diff", "--binary", "--no-renames", base, "--", *paths, check=True).stdout


@contextlib.contextmanager
def release_checkout[S: Checkout](
    sb: S, base: str, overlay: Sequence[str] = (), extra: str = ""
) -> Generator[S]:
    """A disposable checkout of `base` with `overlay` (paths) copied from the run's worktree and the patch
    `extra` applied; yields the sandbox working there. The run's worktree is only read."""
    wt = sb.worktree
    discard_stale(wt)
    path = wt.parent / f"{PREFIX}{uuid.uuid4().hex[:10]}"
    hostgit.run(wt, "worktree", "add", "-q", "--detach", str(path), base, check=True)
    try:
        for diff in (patch(wt, base, overlay), extra):
            if diff:
                hostgit.run(path, "apply", "--binary", "--whitespace=nowarn", "-", input=diff, check=True)
        yield sb.checkout(path)  # pyright: ignore[reportReturnType]
    finally:
        _discard(wt, path)


def changes(worktree: Path, base: str) -> dict[str, str]:
    """Path → git status letter (A, M, D, T) of the worktree against `base`; renames as a delete plus an add."""
    hostgit.run(worktree, "add", "-A", "--intent-to-add", ".")
    raw = hostgit.run(
        worktree, "diff", "--name-status", "--no-renames", "-z", base, "--", ".", check=True
    ).stdout
    parts = [p for p in raw.split("\0") if p]
    return {parts[i + 1]: parts[i][:1] for i in range(0, len(parts) - 1, 2)}


def classify(path: str, status: str) -> PathClass:
    if LOCKFILES.search(path):
        return "lockfile"
    if CI.search(path):
        return "ci"
    if HARNESS.search(path):
        return "harness"
    if is_test_path(path):
        return "new_test" if status == "A" else "modified_test"
    return "source"


def classify_changes(worktree: Path, base: str) -> dict[str, list[str]]:
    """The worktree's changed paths against `base`, by class (only non-empty classes)."""
    out: dict[str, list[str]] = {}
    for path, status in sorted(changes(worktree, base).items()):
        out.setdefault(classify(path, status), []).append(path)
    return out


def protected(classes: dict[str, list[str]]) -> list[str]:
    """`class: path` for each change that keeps a PR a flagged draft."""
    return [f"{c}: {p}" for c in PROTECTED for p in classes.get(c, [])]


def proof_paths(classes: dict[str, list[str]]) -> list[str]:
    """What the proof runs with: the source change and the new tests; everything else as in the release."""
    return [*classes.get("source", []), *classes.get("new_test", [])]
