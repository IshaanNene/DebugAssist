"""Git operations on the MiniRide target repos (submodules under targets/)."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from debugassist.scenarios.catalog import ROOT

COMPOSE_SERVICES = {"miniride-client": ["client"], "miniride-services": ["dispatch", "payments", "gateway"]}
AUTHOR = re.compile(r"^From: (.+?) <([^>]+)>$", re.M)


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    out = subprocess.run(cmd, cwd=cwd, env={**os.environ, **(env or {})}, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed in {cwd}:\n{out.stdout}\n{out.stderr}")
    return out.stdout.strip()


@dataclass(frozen=True)
class TargetRepo:
    name: str
    base_dir: Path = ROOT / "targets"

    @property
    def path(self) -> Path:
        return self.base_dir / self.name

    @property
    def services(self) -> list[str]:
        return COMPOSE_SERVICES.get(self.name, [])

    def git(self, *args: str, env: dict[str, str] | None = None) -> str:
        return run(["git", *args], self.path, env)

    def is_clean(self) -> bool:
        return self.git("status", "--porcelain", "--untracked-files=no") == ""

    def head(self) -> str:
        return self.git("rev-parse", "--abbrev-ref", "HEAD")

    def checkout_release(self, base: str, release: str) -> str:
        branch = f"release/{release}"
        self.git("checkout", "-q", "-B", branch, base)
        return branch

    def apply_patch(self, patch: Path) -> None:
        m = AUTHOR.search(patch.read_text())
        env = {"GIT_COMMITTER_NAME": m.group(1), "GIT_COMMITTER_EMAIL": m.group(2)} if m else {}
        try:
            self.git("am", "-q", "--3way", "--committer-date-is-author-date", str(patch), env=env)
        except RuntimeError:
            self.git("am", "--abort")
            raise

    def release(self, version: str) -> None:
        tag = f"v{version}"
        if tag in self.git("tag", "--list", tag).splitlines():
            self.git("tag", "-d", tag)
        run(["./scripts/release.sh", version], self.path)

    def checkout_ref(self, ref: str) -> str:
        """Detached checkout (a bot branch may be checked out in a run's worktree). Returns the sha."""
        self.git("checkout", "-q", "--detach", ref)
        return self.git("rev-parse", "--short", "HEAD").strip()

    def checkout_main(self) -> None:
        self.git("checkout", "-q", "main")

    def export_tree(self, ref: str, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        archive = subprocess.run(["git", "archive", ref], cwd=self.path, capture_output=True, check=True)
        subprocess.run(["tar", "-x", "-C", str(dest)], input=archive.stdout, check=True)

    def push(self, branch: str, tag: str | None) -> None:
        self.git("push", "-q", "-f", "origin", branch)
        if tag:
            self.git("push", "-q", "-f", "origin", tag)
