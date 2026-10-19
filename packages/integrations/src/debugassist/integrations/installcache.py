"""Install cache (ROADMAP-100 048): dependencies installed once per (image, setup command, manifests) and reused.

A run's install step (`Sandbox.install`, the one container with network) fills the worktree's ignored directories:
node_modules, .venv, the uv/go/pnpm caches. Runs of the same release, and of releases whose manifests and lockfiles
did not change, install the same thing. The cache keeps a copy of those directories under `.data/install-cache/<key>`,
where the key is a hash of the image, the setup command, the component and the bytes of every tracked manifest and
lockfile; a later run with the same key copies them in instead of installing.

Trust: an entry is saved only from a fresh worktree right after its install — before any agent has run a command
there — and the agent never sees the cache, only a copy-on-write (or full) copy of it, never hard links. The key
assumes the setup command's result depends on the manifests and lockfiles, not on other source files; a repository
whose install builds from source should set `DA_INSTALL_CACHE=0`.

    DA_INSTALL_CACHE      1 (default) | 0 — use and fill the cache
    DA_INSTALL_CACHE_MAX  entries kept, least recently used dropped first (default 8)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from debugassist.core.guards import GuardError
from debugassist.core.policy import ROOT
from debugassist.core.workspace import Workspace

CACHE = ROOT / ".data" / "install-cache"
KEY_VERSION = 1
MANIFESTS = re.compile(
    r"(^|/)(package\.json|pnpm-lock\.yaml|pnpm-workspace\.yaml|package-lock\.json|npm-shrinkwrap\.json|yarn\.lock"
    r"|\.npmrc|\.nvmrc|\.node-version|pyproject\.toml|uv\.lock|poetry\.lock|requirements[^/]*\.txt|setup\.py"
    r"|setup\.cfg|\.python-version|go\.mod|go\.sum|go\.work|go\.work\.sum)$"
)
# Ignored directories that are run output, not installed dependencies.
NOT_DEPENDENCIES = {".da-e2e", "test-results"}


def enabled() -> bool:
    return os.environ.get("DA_INSTALL_CACHE", "1").strip().lower() not in {"0", "false", "no", "off"}


def max_entries() -> int:
    try:
        return max(1, int(os.environ.get("DA_INSTALL_CACHE_MAX", "8")))
    except ValueError:
        return 8


def key(ws: Workspace, image: str, setup: str, workdir: str) -> str | None:
    """The cache key for installing in `ws` now, or None when it cannot be told (not a git worktree)."""
    listing = ws.git("ls-files", "-z")
    if listing.returncode:
        return None
    h = hashlib.sha256(json.dumps([KEY_VERSION, image, setup, workdir.strip("/") or "."]).encode())
    for rel in sorted(p for p in listing.stdout.split("\0") if p and MANIFESTS.search(p)):
        try:
            data = ws.path(rel).read_bytes()
        except (GuardError, OSError):  # a manifest that is a link out, or missing: part of the key as such
            data = b"\0missing"
        h.update(rel.encode() + b"\0" + hashlib.sha256(data).digest())
    return h.hexdigest()[:32]


def dependency_dirs(dirs: list[str]) -> list[str]:
    return sorted(d for d in dirs if Path(d).name not in NOT_DEPENDENCIES)


def copy_tree(src: Path, dst: Path) -> None:
    """Copy a directory without following symlinks: a clone (copy-on-write) where the filesystem has one, else a
    full copy. Never hard links — the agent's commands write to the copy, and the cache must not change."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = (
        ["cp", "-cRP", str(src), str(dst)]
        if sys.platform == "darwin"
        else ["cp", "-a", "--reflink=auto", str(src), str(dst)]
        if sys.platform.startswith("linux")
        else None
    )
    if cmd and subprocess.run(cmd, capture_output=True).returncode == 0:
        return
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst, symlinks=True)


@dataclass(frozen=True)
class Entry:
    key: str
    path: Path

    @property
    def manifest(self) -> Path:
        return self.path / "manifest.json"

    def dirs(self) -> list[str]:
        return list(json.loads(self.manifest.read_text())["dirs"])


def lookup(cache_key: str, root: Path | None = None) -> Entry | None:
    root = root or CACHE
    entry = Entry(cache_key, root / cache_key)
    return entry if entry.manifest.is_file() else None


def restore(entry: Entry, ws: Workspace) -> list[str]:
    """Copy the entry's directories into the worktree; returns them. The entry's mtime marks it recently used."""
    dirs = entry.dirs()
    for rel in dirs:
        dst = ws.path(rel)  # confined: a manifest naming `..` or `.git` is refused
        copy_tree(entry.path / "dirs" / rel, dst)
    os.utime(entry.manifest)
    return dirs


def save(
    cache_key: str, ws: Workspace, dirs: list[str], seconds: float, root: Path | None = None
) -> Entry | None:
    """Store `dirs` (relative to the worktree) under `cache_key`; None if another run stored it first."""
    root = root or CACHE
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / f".tmp-{uuid.uuid4().hex[:10]}"
    try:
        for rel in dirs:
            copy_tree(ws.path(rel), tmp / "dirs" / rel)
        (tmp / "manifest.json").write_text(
            json.dumps(
                {"dirs": dirs, "install_seconds": round(seconds, 1), "saved_at": time.time()}, indent=2
            )
        )
        try:
            tmp.rename(root / cache_key)
        except OSError:  # stored by a concurrent run with the same key
            return None
        return Entry(cache_key, root / cache_key)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def prune(keep: int | None = None, root: Path | None = None) -> list[str]:
    """Drop least recently used entries beyond `keep`; returns their keys."""
    root = root or CACHE
    keep = max_entries() if keep is None else keep
    entries = sorted(
        (p for p in root.glob("*") if (p / "manifest.json").is_file()),
        key=lambda p: (p / "manifest.json").stat().st_mtime,
        reverse=True,
    )
    dropped: list[str] = []
    for p in entries[keep:]:
        shutil.rmtree(p, ignore_errors=True)
        dropped.append(p.name)
    return dropped
