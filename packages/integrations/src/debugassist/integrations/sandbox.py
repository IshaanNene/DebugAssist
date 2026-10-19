"""Sandbox: a disposable git worktree per run, and a network-less container to run commands in.

The agent edits files only inside the worktree (paths are confined by the guards) and its commands
run in a container with the worktree mounted and `--network none`. Dependencies are installed once
per run with network, before the agent starts.

The worktree is untrusted input to the host: the container runs as the host user with no capabilities, the
worktree's `.git` is mounted read-only, and host git goes through `core.hostgit`, which never discovers the
repository from the worktree.
"""

from __future__ import annotations

import dataclasses
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from debugassist.core import tracing
from debugassist.core.guards import check_command
from debugassist.core.policy import ROOT
from debugassist.core.workspace import Workspace

RUNS = ROOT / ".data" / "runs"
IMAGES = {
    "typescript": "node:22-alpine",
    "python": "ghcr.io/astral-sh/uv:python3.13-trixie-slim",
    "go": "golang:1.26-alpine",
}


@dataclass
class CommandResult:
    command: str
    exit_code: int
    output: str


@dataclass
class Sandbox:
    run_id: str
    repo_path: Path  # the target repo (submodule checkout)
    repo: str  # owner/name on GitHub
    language: str = "typescript"
    # A disposable checkout to work in instead of the run's worktree (`pipeline.release.release_checkout`), and
    # the run worktree's dependency dirs (node_modules, .venv, …) mounted into it at the same paths.
    root: Path | None = None
    shared: tuple[str, ...] = ()

    @property
    def worktree(self) -> Path:
        return self.root or self.run_worktree

    @property
    def workspace(self) -> Workspace:
        """Host access to the worktree — git, reads, walks — through the guards (core.workspace)."""
        return Workspace(self.worktree)

    @property
    def run_worktree(self) -> Path:
        """The run's own worktree, where dependencies were installed."""
        return RUNS / self.run_id / "repo"

    def checkout(self, root: Path) -> Sandbox:
        """This sandbox, working in `root` (another checkout of the repository) with the run's dependencies."""
        return dataclasses.replace(self, root=root, shared=tuple(self.dependency_dirs()))

    def dependency_dirs(self) -> list[str]:
        """The run worktree's ignored directories (installed dependencies, caches), relative to it. The worktree
        is untrusted: a directory reached through a symlink would mount some other host path, so none is."""
        wt = self.run_worktree
        raw = (
            Workspace(wt)
            .git("status", "--porcelain=v1", "-z", "--ignored=matching", "--untracked-files=normal")
            .stdout
        )
        out: list[str] = []
        for entry in raw.split("\0"):
            rel = entry[3:].rstrip("/")
            if not (entry.startswith("!! ") and entry.endswith("/") and rel and ".git" not in rel.split("/")):
                continue
            if (wt / rel).resolve() == wt.resolve() / rel and (wt / rel).is_dir():
                out.append(rel)
        return out

    def mounts(self) -> list[str]:
        """`docker run` volume flags for the shared dependency dirs (none for the run's own worktree)."""
        out: list[str] = []
        for rel in self.shared:
            (self.worktree / rel).mkdir(parents=True, exist_ok=True)  # the mount point
            out += ["-v", f"{self.run_worktree / rel}:/work/{rel}"]
        return out

    def _git(self, *args: str, cwd: Path | None = None) -> str:
        out = Workspace(cwd or self.worktree).git(*args)
        if out.returncode:
            raise RuntimeError(f"git {' '.join(args)}: {out.stderr.strip()}")
        return out.stdout.strip()

    def create(self, ref: str, branch: str) -> None:
        if self.worktree.exists():
            self.destroy()
        self.worktree.parent.mkdir(parents=True, exist_ok=True)
        # A previous run on the same issue may still hold the bot branch in its worktree.
        listing = self._git("worktree", "list", "--porcelain", cwd=self.repo_path)
        for block in listing.split("\n\n"):
            if f"branch refs/heads/{branch}" in block:
                path = block.splitlines()[0].removeprefix("worktree ")
                try:
                    self._git("worktree", "remove", "--force", path, cwd=self.repo_path)
                except RuntimeError:
                    # Files a container was still writing can make git's own delete fail ("Directory not
                    # empty"); delete the directory ourselves and let `prune` drop the registration.
                    shutil.rmtree(path, ignore_errors=True)
        self._git("worktree", "prune", cwd=self.repo_path)
        self._git("worktree", "add", "-q", "-B", branch, str(self.worktree), ref, cwd=self.repo_path)
        exclude = Path(self._git("rev-parse", "--git-path", "info/exclude"))
        exclude = exclude if exclude.is_absolute() else self.worktree / exclude
        exclude.parent.mkdir(parents=True, exist_ok=True)
        lines = exclude.read_text().splitlines() if exclude.exists() else []
        for pat in (
            ".corepack/",
            ".pnpm-store/",
            "node_modules/",
            ".venv/",
            ".cache/",
            "go-build/",
            ".da-e2e/",
            "test-results/",
        ):
            if pat not in lines:
                lines.append(pat)
        exclude.write_text("\n".join(lines) + "\n")

    def destroy(self) -> None:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(self.worktree)],
            cwd=self.repo_path,
            capture_output=True,
        )

    def run(
        self, command: str, *, workdir: str = ".", network: bool = False, timeout: int = 600
    ) -> CommandResult:
        """Run a command in the language image with the worktree mounted at /work."""
        check_command(command)
        image = IMAGES[self.language]
        # Not root, so corepack cannot write /usr/local/bin: its shims go to a directory on PATH under /tmp.
        setup = (
            "export PATH=/tmp/bin:$PATH; mkdir -p /tmp/bin && "
            "corepack enable --install-directory /tmp/bin >/dev/null 2>&1; "
            if self.language == "typescript"
            else ""
        )
        cmd = [
            "docker",
            "run",
            "--rm",
            *self.hardening(),
            "-v",
            f"{self.worktree}:/work",
            *self.git_mount(),
            *self.mounts(),
            "-w",
            f"/work/{workdir}".rstrip("/."),
            "--network",
            "bridge" if network else "none",
            "--memory",
            "2g",
            "--cpus",
            "2",
            "-e",
            "CI=1",
            "-e",
            "HOME=/tmp",
            "-e",
            "COREPACK_HOME=/work/.corepack",
            "-e",
            "npm_config_store_dir=/work/.pnpm-store",
            "-e",
            "UV_CACHE_DIR=/work/.cache/uv",
            "-e",
            # Projects that pin `python-preference = "only-managed"` download their interpreter at install time;
            # keep it in the worktree so later (offline) containers still find it, like the package cache.
            "UV_PYTHON_INSTALL_DIR=/work/.cache/uv-python",
            "-e",
            "GOMODCACHE=/work/.cache/gomod",
            "-e",
            "GOCACHE=/work/.cache/go-build",
            image,
            "sh",
            "-c",  # not a login shell: Alpine's /etc/profile resets PATH (drops /usr/local/go/bin)
            setup + command,
        ]
        with tracing.span("sandbox", kind="tool", **{"tool.name": "sandbox", "input.value": command}) as sp:
            try:
                # test runners print binary noise and ANSI art: never let a decode error lose the result
                p = subprocess.run(
                    cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
                )
                result = CommandResult(command, p.returncode, (p.stdout + p.stderr)[-12000:])
            except subprocess.TimeoutExpired:
                result = CommandResult(command, 124, f"timed out after {timeout}s")
            tracing.set_attributes(sp, exit_code=result.exit_code, **{"output.value": result.output[-2000:]})
            return result

    def hardening(self) -> list[str]:
        """Least privilege for the container: the host user's ids (so files it writes are not root-owned and
        git's ownership checks keep their meaning), no capabilities, no privilege gain, a process cap."""
        user = [] if os.name == "nt" else ["--user", f"{os.getuid()}:{os.getgid()}"]
        return [*user, "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "512"]

    def git_mount(self) -> list[str]:
        """Mount the worktree's `.git` read-only over itself, so commands cannot replace it (the host never
        trusts it either — see `core.hostgit`)."""
        dot = self.worktree / ".git"
        return ["-v", f"{dot}:/work/.git:ro"] if dot.exists() and not dot.is_symlink() else []

    def install(self, setup: str, workdir: str = ".") -> CommandResult:
        """Install dependencies (the one step allowed network access)."""
        image = IMAGES[self.language]
        if subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode:
            # Pull first, outside the install's timeout (an image missing after a Docker reset).
            p = subprocess.run(["docker", "pull", "-q", image], capture_output=True, text=True, timeout=900)
            if p.returncode:
                return CommandResult(f"docker pull {image}", p.returncode, (p.stdout + p.stderr)[-4000:])
        return self.run(setup, workdir=workdir, network=True, timeout=900)

    def diff(self, base: str = "HEAD") -> str:
        self._git("add", "-A", "--intent-to-add", ".")
        return self._git("diff", base, "--", ".")

    def commit(
        self, message: str, author: str = "DebugAssist Bot <debugassist-bot@users.noreply.github.com>"
    ) -> str:
        self._git("add", "-A", "--", ".")
        name, email = author.rsplit(" <", 1)
        self._git(
            "-c", f"user.name={name}", "-c", f"user.email={email.rstrip('>')}", "commit", "-q", "-m", message
        )
        return self._git("rev-parse", "HEAD")


def shell_join(parts: list[str]) -> str:
    return " ".join(shlex.quote(p) for p in parts)
