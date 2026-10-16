"""Guards for agent tool calls: shell commands and file paths.

These are a denylist and catch mistakes, not an adversary (any interpreter gets past a regex). The boundary is
the network-less, unprivileged container on a disposable worktree, and host code that treats that worktree as
untrusted (`core.hostgit`, `walk_files`). There is no egress guard: the container has no network at all.
"""

from __future__ import annotations

import os
import re
import shlex
from collections.abc import Collection
from pathlib import Path

DENY_COMMANDS = [
    (
        re.compile(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)\s+(/|~|\$HOME|\.\.)"),
        "recursive delete outside the worktree",
    ),
    (
        re.compile(r"\bgit\s+(push|remote|config\s+--global|credential)"),
        "git push/remote/credential changes are done by the pipeline, not the agent",
    ),
    (
        re.compile(r"\b(curl|wget|nc|ncat|telnet|ssh|scp|rsync|ftp)\b"),
        "network tools are not available in the sandbox",
    ),
    (
        re.compile(r"\b(sudo|su|chmod\s+777|chown|mkfs|dd\s+if=|shutdown|reboot)\b"),
        "privileged or destructive command",
    ),
    (re.compile(r"(^|[;&|]\s*)(env|printenv|set)\s*($|[;&|])"), "dumping the environment"),
    (
        re.compile(r"\b(docker|kubectl|aws|gcloud|az|gh)\b"),
        "infrastructure CLIs are not available to the agent",
    ),
    (re.compile(r":\(\)\s*\{"), "fork bomb"),
]
SECRET_PATHS = re.compile(
    r"(^|/)(\.env(\..+)?|id_rsa|id_ed25519|\.npmrc|\.netrc|\.pypirc|credentials(\.json)?|.*\.pem|.*\.key)$",
    re.I,
)


class GuardError(PermissionError):
    pass


def check_command(command: str) -> None:
    for pattern, why in DENY_COMMANDS:
        if pattern.search(command):
            raise GuardError(f"blocked: {why}")
    try:
        for token in shlex.split(command):
            if SECRET_PATHS.search(token):
                raise GuardError(f"blocked: reading secrets ({token})")
    except ValueError as exc:
        raise GuardError(f"blocked: unparseable command ({exc})") from exc


def confine(root: Path, rel: str) -> Path:
    """Resolve `rel` inside `root`; refuse escapes and secret files."""
    p = (root / rel).resolve()
    if p != root.resolve() and root.resolve() not in p.parents:
        raise GuardError(f"blocked: {rel} is outside the worktree")
    if SECRET_PATHS.search(str(p)):
        raise GuardError(f"blocked: {rel} looks like a secret file")
    if ".git" in p.relative_to(root.resolve()).parts:
        raise GuardError("blocked: .git internals are off limits")
    return p


def walk_files(root: Path, skip: Collection[str] = ()) -> list[Path]:
    """Regular files under `root`, sorted, reached without following a symlink and never secret files.

    Host-side tools read the worktree the sandboxed agent writes: a symlink there may point anywhere on the
    host (`notes.txt -> ../../../../.env`), so a walk must neither follow nor return one.
    """
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)
        dirnames[:] = [n for n in dirnames if n not in skip and n != ".git" and not (here / n).is_symlink()]
        for name in filenames:
            p = here / name
            if p.is_symlink() or not p.is_file() or SECRET_PATHS.search(name):
                continue
            out.append(p)
    return sorted(out)
