"""Guards for agent tool calls: shell commands, file paths and network egress.

Defence in depth: commands also run in a network-less container on a disposable worktree.
"""

from __future__ import annotations

import re
import shlex
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


ALLOWED_HOSTS = {"localhost", "127.0.0.1", "openrouter.ai", "api.cloudflare.com", "api.github.com"}


def check_egress(host: str, allowed: set[str] = ALLOWED_HOSTS) -> None:
    if host not in allowed and not any(host.endswith("." + a) for a in allowed):
        raise GuardError(f"blocked: egress to {host}")
