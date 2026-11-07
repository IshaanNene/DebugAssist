"""`make doctor` (ROADMAP-100 096): is this machine ready to run DebugAssist? Checks, never changes anything.

Prints one line per check (ok / warn / FAIL) and exits non-zero only on a FAIL. `.env` is read for key *names*;
values are never printed.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORTS = {
    8400: "API",
    3000: "dashboard",
    8080: "MiniRide client",
    5432: "Postgres",
    6379: "Redis",
    6006: "Phoenix",
}
KEYS = {
    "an LLM key": ("OPEN_ROUTER_API_KEY", "GROQ_CLOUD_API"),
    "Clef (Workers AI)": ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_KEY"),
    "GitHub pushes": ("GITHUB_TOKEN",),
}
DISK_MAX = 0.90  # above this, git objects, uv caches and Docker layers start failing in odd ways
# Path parts of folders that a sync client owns. A synced repo loses files and git objects to eviction, and gets
# "conflict copies" and hidden .pth files (docs/LESSONS.md).
SYNCED_PARTS = ("Mobile Documents", "CloudStorage", "Dropbox", "OneDrive", "Google Drive")
FILE_PROVIDER_XATTR = "com.apple.file-provider-domain-id"  # iCloud Desktop & Documents, File Provider clients
results: list[tuple[str, str, str]] = []


def check(name: str, status: str, detail: str = "") -> None:
    results.append((status, name, detail))


def env_names() -> set[str]:
    f = ROOT / ".env"
    if not f.is_file():
        return set()
    names: set[str] = set()
    for line in f.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and not key.lstrip().startswith("#") and value.strip():
            names.add(key.strip())
    return names


def macos_xattrs(path: Path) -> set[str]:
    xattr = shutil.which("xattr")
    if not xattr:
        return set()
    out = subprocess.run([xattr, str(path)], capture_output=True, text=True)  # noqa: S603 - fixed argv
    return set(out.stdout.split()) if out.returncode == 0 else set()


def synced_folder(path: Path, xattrs: Callable[[Path], set[str]] = macos_xattrs) -> str | None:
    """The synced ancestor of `path` and why, or None. Checks the path and every parent."""
    for p in (path, *path.parents):
        if p.name in SYNCED_PARTS:
            return f"{p} (a sync client's folder)"
        if FILE_PROVIDER_XATTR in xattrs(p):
            return f"{p} (synced by a file provider, e.g. iCloud Desktop & Documents)"
    return None


def disk_used(total: int, used: int, free: int) -> float:
    """Used share as `df` reports it (APFS: used / (used + available))."""
    return used / (used + free) if used + free else 0.0


def main() -> int:
    v = sys.version_info
    check("Python ≥ 3.13", "ok" if v >= (3, 13) else "FAIL", f"{v.major}.{v.minor}")
    for tool, need in (("uv", "FAIL"), ("git", "FAIL"), ("docker", "warn"), ("pnpm", "warn")):
        check(
            f"{tool} on PATH", "ok" if shutil.which(tool) else need, "" if shutil.which(tool) else "not found"
        )
    if docker := shutil.which("docker"):
        up = subprocess.run(  # noqa: S603 - the resolved docker binary, fixed arguments
            [docker, "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True
        )
        check(
            "Docker daemon",
            "ok" if up.returncode == 0 else "warn",
            up.stdout.strip() or "not running: sandboxed runs need it",
        )
    for sub in ("targets/miniride-client", "targets/miniride-services"):
        present = (ROOT / sub / ".git").exists()
        check(
            f"submodule {sub}",
            "ok" if present else "warn",
            "" if present else "missing (git submodule update --init)",
        )
    where = synced_folder(ROOT)
    check(
        "repo outside synced folders",
        "FAIL" if where else "ok",
        f"{where}: move the repo (e.g. ~/src/DebugAssist)" if where else str(ROOT),
    )
    du = shutil.disk_usage(ROOT)
    share = disk_used(du.total, du.used, du.free)
    check(
        f"disk under {DISK_MAX:.0%} full",
        "FAIL" if share > DISK_MAX else "ok",
        f"{share:.0%} used, {du.free / 2**30:.0f} GiB free",
    )
    names = env_names()
    check(
        ".env",
        "ok" if (ROOT / ".env").is_file() else "warn",
        "" if names else "absent: everything runs in mock mode",
    )
    for what, keys in KEYS.items():
        have = [k for k in keys if k in names]
        check(f"{what} configured", "ok" if have else "warn", ", ".join(have) or "mock mode")
    for port, what in PORTS.items():
        with socket.socket() as s:
            s.settimeout(0.2)
            busy = s.connect_ex(("127.0.0.1", port)) == 0
        check(f"port {port} ({what})", "ok", "in use (already running?)" if busy else "free")
    width = max(len(n) for _, n, _ in results)
    for status, name, detail in results:
        print(f"{status:>4}  {name:<{width}}  {detail}")
    return 1 if any(s == "FAIL" for s, _, _ in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
