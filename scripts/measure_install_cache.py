"""Measure the install cache (ROADMAP-100 048): a cold install against a restore, per repository.

    uv run --no-sync python scripts/measure_install_cache.py [--base DIR] [repo …]   # needs Docker

For each target checkout: a fresh worktree installs with network (miss, saved), a second fresh worktree restores
from the cache (hit); both then run the component's test command offline, so a restore that left something out
shows up as a different exit code. The entries go to a separate cache directory, emptied first, so every number
is a cold install against its own restore. `--base` puts the worktrees and the cache in DIR instead of `.data/` (a
directory outside a synced folder: iCloud Drive throttles the creation of many small files). Writes
evals/reports/install-cache.json.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from debugassist.core.policy import ROOT
from debugassist.core.workspace import Workspace
from debugassist.integrations import installcache
from debugassist.integrations.sandbox import Sandbox

REPOS = ["miniride-client", "semver", "go-runewidth", "radashi"]
OUT = ROOT / "evals" / "reports" / "install-cache.json"


class MeasureSandbox(Sandbox):
    base: Path = ROOT / ".data" / "install-cache-measure"

    @property
    def run_worktree(self) -> Path:
        return self.base / "runs" / self.run_id / "repo"


def _size(path: Any) -> int:
    return sum(f.lstat().st_size for f in path.rglob("*") if f.is_file() and not f.is_symlink())


def measure(repo: str) -> dict[str, Any]:
    path = ROOT / "targets" / repo
    ws = Workspace(path)
    cfg = yaml.safe_load(ws.read(".DebugAssist/pipeline.yaml"))
    comp = next(iter(cfg["components"].values()))
    workdir = str(comp.get("path", "."))
    ref = ws.git_out("rev-parse", "HEAD")
    rec: dict[str, Any] = {
        "repo": repo,
        "language": comp["language"],
        "setup": comp["setup"],
        "ref": ref[:12],
    }
    runs: dict[str, MeasureSandbox] = {}
    try:
        for phase in ("cold", "warm"):
            sb = MeasureSandbox(
                f"measure-install-{repo}-{phase}", path, f"local/{repo}", language=comp["language"]
            )
            sb.create(ref, f"measure-install-{phase}")
            runs[phase] = sb
            started = time.monotonic()
            res = sb.install(str(comp["setup"]), workdir=workdir)
            rec[f"{phase}_seconds"] = round(time.monotonic() - started, 1)
            rec[f"{phase}_install_exit"] = res.exit_code
            rec[f"{phase}_cache_hit"] = "install cache hit" in res.output
            if res.exit_code:
                rec[f"{phase}_tail"] = res.output[-800:]
                return rec
            test = sb.run(str(comp["test"]), workdir=workdir, timeout=900)
            rec[f"{phase}_test_exit"] = test.exit_code
        entry = next(installcache.CACHE.glob("*/manifest.json")).parent
        rec["cache_entry_mb"] = round(_size(entry) / 1e6, 1)
        rec["cached_dirs"] = json.loads((entry / "manifest.json").read_text())["dirs"]
        return rec
    finally:
        for sb in runs.values():
            sb.destroy()
            shutil.rmtree(sb.run_worktree.parent, ignore_errors=True)


def main(args: list[str]) -> None:
    base = ROOT / ".data" / "install-cache-measure"
    if args[:1] == ["--base"]:
        base, args = Path(args[1]).resolve() / "install-cache-measure", args[2:]
    repos = args or REPOS
    MeasureSandbox.base = base
    results: list[dict[str, Any]] = []
    for repo in repos:
        installcache.CACHE = base / repo
        shutil.rmtree(installcache.CACHE, ignore_errors=True)
        print(f"{repo} …", flush=True)
        rec = measure(repo)
        print(json.dumps(rec), flush=True)
        results.append(rec)
    shutil.rmtree(base, ignore_errors=True)
    OUT.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "command": " ".join(
                    ["uv run --no-sync python scripts/measure_install_cache.py", *sys.argv[1:]]
                ),
                "platform": sys.platform,
                "outside_icloud": not str(base).startswith(str(Path.home() / "Desktop")),
                "results": results,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])
