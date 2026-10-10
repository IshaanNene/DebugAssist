"""Sandbox: a disposable git worktree per run, and a network-less container to run commands in.

The agent edits files only inside the worktree (paths are confined by the guards) and its commands
run in a container with the worktree mounted and `--network none`. Dependencies are installed once
per run with network, before the agent starts.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from debugassist.core import tracing
from debugassist.core.guards import check_command
from debugassist.core.policy import ROOT

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

    @property
    def worktree(self) -> Path:
        return RUNS / self.run_id / "repo"

    def _git(self, *args: str, cwd: Path | None = None) -> str:
        out = subprocess.run(["git", *args], cwd=cwd or self.worktree, capture_output=True, text=True)
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
                self._git("worktree", "remove", "--force", path, cwd=self.repo_path)
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
        setup = "corepack enable >/dev/null 2>&1; " if self.language == "typescript" else ""
        cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{self.worktree}:/work",
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
