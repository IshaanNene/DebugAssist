"""A run's worktree as host code may touch it (ROADMAP-100 036): one object for git, reads, writes and walks.

The worktree is mounted read-write into the sandbox, so everything in it is untrusted. Every host access goes
through here, and so through the same three guards:
- git runs through `hostgit`, which never lets git discover the repository (or its config, hooks, filters) from
  the worktree;
- a file is reached through `guards.confine`: no `..`, no symlink out of the worktree, no `.git` internals, no
  secret files — a path that fails is treated as absent by the queries and refused by reads and writes;
- a walk never follows or returns a symlink (`guards.walk_files`).
"""

from __future__ import annotations

import subprocess
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

from debugassist.core import hostgit
from debugassist.core.guards import GuardError, confine, walk_files


@dataclass(frozen=True)
class Workspace:
    root: Path

    # ---- git -------------------------------------------------------------------------------------

    def git(
        self,
        *args: str,
        input: str | None = None,
        check: bool = False,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """`git <args>` for this worktree (hostgit: the git dir is resolved and verified, never discovered)."""
        return hostgit.run(self.root, *args, input=input, check=check, extra_env=extra_env)

    def git_out(self, *args: str) -> str:
        """The stripped stdout of a git command that may fail ('' when it does)."""
        return self.git(*args).stdout.strip()

    def has_ref(self, ref: str) -> bool:
        return self.git("rev-parse", "--verify", "-q", ref).returncode == 0

    def show(self, ref: str, rel: str) -> str | None:
        """A file as it is at `ref` (the object database, not the working tree), or None if it is not there."""
        out = self.git("show", f"{ref}:{rel}")
        return out.stdout if out.returncode == 0 else None

    def branch(self) -> str:
        return self.git("branch", "--show-current", check=True).stdout.strip()

    def status(self) -> list[str]:
        """Paths with changes, untracked files included (porcelain v1, NUL-separated; renames give both paths)."""
        raw = self.git("status", "--porcelain=v1", "-z", "--untracked-files=all", check=True).stdout
        out: list[str] = []
        entries = iter(raw.split("\0"))
        for entry in entries:
            if not entry:
                continue
            out.append(entry[3:])
            if (
                "R" in entry[:2] or "C" in entry[:2]
            ):  # a rename or copy (either column) is followed by its source
                src = next(entries, "")
                if src:
                    out.append(src)
        return out

    def dirty(self) -> bool:
        return bool(self.git("status", "--porcelain", check=True).stdout.strip())

    def apply(self, diff: str) -> None:
        self.git("apply", "--whitespace=nowarn", "-", input=diff, check=True)

    def reset(self, ref: str) -> None:
        """Tracked files back to `ref` and untracked ones removed (ignored ones — installed dependencies — kept)."""
        self.git("reset", "-q", "--hard", ref, check=True)
        self.git("clean", "-qfd")

    # ---- files -----------------------------------------------------------------------------------

    def path(self, rel: str) -> Path:
        """`rel` resolved inside the worktree; GuardError when it would leave it (or reach .git or a secret)."""
        return confine(self.root, rel)

    def _safe(self, rel: str) -> Path | None:
        try:
            return self.path(rel)
        except GuardError:
            return None

    def is_file(self, rel: str) -> bool:
        p = self._safe(rel)
        return p is not None and p.is_file()

    def is_dir(self, rel: str) -> bool:
        p = self._safe(rel)
        return p is not None and p.is_dir()

    def is_symlink(self, rel: str) -> bool:
        """Whether `rel` itself is a symlink (checked before resolving, so a link out is still reported)."""
        return (self.root / rel).is_symlink()

    def read(self, rel: str) -> str:
        return self.path(rel).read_text()

    def write(self, rel: str, text: str) -> Path:
        p = self.path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def remove(self, rel: str) -> None:
        """Delete the entry at `rel`. A symlink is removed itself — its target, wherever it points, is never
        touched — as long as the link sits inside the worktree; any other path must resolve inside it."""
        link = self.root / rel
        if link.is_symlink():
            if self._safe(str(Path(rel).parent)) is not None and ".git" not in Path(rel).parts:
                link.unlink()
            return
        p = self._safe(rel)
        if p is not None:
            p.unlink(missing_ok=True)

    def mtime(self, rel: str) -> float:
        return self.path(rel).stat().st_mtime

    def glob(self, rel_dir: str, pattern: str) -> list[str]:
        """Files matching `pattern` directly in `rel_dir`, relative to the worktree; symlinks skipped."""
        d = self._safe(rel_dir)
        if d is None or not d.is_dir():
            return []
        root = self.root.resolve()
        return sorted(str(p.relative_to(root)) for p in d.glob(pattern) if p.is_file() and not p.is_symlink())

    def walk(self, rel_dir: str = ".", skip: Collection[str] = ()) -> list[Path]:
        """Regular files under `rel_dir`, never through a symlink, never .git or secret files."""
        d = self._safe(rel_dir)
        return walk_files(d, skip) if d is not None and d.is_dir() else []
