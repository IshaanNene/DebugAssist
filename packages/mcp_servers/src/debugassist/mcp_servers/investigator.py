"""DebugAssist as an MCP server for coding agents (ROADMAP-100 080): Claude Code, Cursor or Codex can ask it to
investigate an issue and read back the root cause and the proof, without knowing the pipeline.

    claude mcp add debugassist -- uv run --directory <checkout> python -m debugassist.mcp_servers.investigator

Tools: `investigate` starts a run (its own process; mock LLM unless asked for live), `runs` lists the runs of an
issue, `report` returns one run's root cause, validation proof, outcome and PR. It reads run state files; it never
writes outside starting a run, and every write that run makes goes through the pipeline's own policy gate.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Literal, cast

from mcp.server.fastmcp import FastMCP

from debugassist.core.policy import ROOT
from debugassist.core.redaction import redact_secrets

mcp = FastMCP("debugassist", log_level="WARNING")
RUNS = ROOT / ".data" / "runs"
JOBS = ROOT / ".data" / "investigator"
CLI = Path(sys.executable).parent / "debugassist"
SAFE_REF = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_:#/."


def _spawn(issue: str, llm: str, log: Path) -> int:
    with log.open("w") as out:
        p = subprocess.Popen(
            [str(CLI), "run", issue, "--llm", llm],
            stdout=out,
            stderr=subprocess.STDOUT,
            cwd=ROOT,
            env=os.environ.copy(),
        )
    return p.pid


@mcp.tool()
def investigate(issue: str, llm: Literal["mock", "live"] = "mock") -> dict[str, Any]:
    """Start a DebugAssist run on an issue (VIT-1001, BD-1003, latest, or GHA:owner/repo#123). Returns at once;
    the run takes minutes. `llm="live"` uses real models and spends money; the default is the mock."""
    if not issue or any(c not in SAFE_REF for c in issue):
        return {"error": f"not an issue reference: {issue!r}"}
    JOBS.mkdir(parents=True, exist_ok=True)
    log = JOBS / f"{time.strftime('%Y%m%d-%H%M%S')}-{issue.replace('/', '_').replace('#', '-')}.log"
    pid = _spawn(issue, llm, log)
    return {"started": True, "issue": issue, "llm": llm, "pid": pid, "log": str(log.relative_to(ROOT)),
            "next": f"call runs(issue={issue!r}) in a minute for its run id, then report(run_id)"}  # fmt: skip


def _state(run_id: str) -> Any:
    """The run's state file as JSON (None when there is no such run)."""
    f = RUNS / run_id / "state.json"
    if "/" in run_id or ".." in run_id or not f.is_file():
        return None
    return json.loads(f.read_text())


def _at(d: Any, *keys: str) -> Any:
    """d[k1][k2]…, or None as soon as a level is missing or not an object (run state is untyped JSON here)."""
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = cast(dict[str, Any], d).get(k)
    return d


@mcp.tool()
def runs(issue: str | None = None, limit: int = 10) -> dict[str, Any]:
    """Runs, newest first (of one issue when given): run id, status and outcome."""
    out: list[dict[str, Any]] = []
    for d in sorted((p for p in RUNS.iterdir() if p.is_dir()), reverse=True) if RUNS.is_dir() else []:
        s = _state(d.name)
        if s is None:
            continue
        if issue and issue not in (_at(s, "issue_ref"), _at(s, "issue", "id")):
            continue
        out.append({"run_id": d.name, "issue": _at(s, "issue_ref"), "status": _at(s, "status"),
                    "outcome": _at(s, "ship", "outcome")})  # fmt: skip
        if len(out) >= min(limit, 50):
            break
    return {"runs": out}


@mcp.tool()
def report(run_id: str) -> dict[str, Any]:
    """One run's root cause (summary, location, claims with evidence ids), the validation proof, and the PR."""
    s = _state(run_id)
    if s is None:
        return {"error": f"no run {run_id}"}
    rca = _at(s, "rca", "output")
    v = _at(s, "validation")

    def run_of(key: str) -> dict[str, Any] | None:
        t = _at(v, key)
        return {"command": _at(t, "command"), "exit_code": _at(t, "exit_code")} if t else None

    claims: list[Any] = _at(rca, "claims") or []
    failures: list[Any] = _at(s, "failures") or []
    body: dict[str, Any] = {
        "run_id": run_id,
        "status": _at(s, "status"),
        "root_cause": {
            "summary": _at(rca, "summary"),
            "category": _at(rca, "category"),
            "location": _at(rca, "location"),
            "claims": [{"text": _at(c, "text"), "evidence": _at(c, "evidence_ids")} for c in claims],
            "fix_direction": _at(rca, "fix_direction"),
        }
        if rca
        else None,
        "validation": {
            "passed": _at(v, "passed"),
            "fails_on_release": run_of("failing_before"),
            "passes_with_fix": run_of("passing_after"),
            "suite": run_of("suite"),
            "flagged": _at(v, "protected") or [],
        }
        if v
        else None,
        "outcome": _at(s, "ship", "outcome"),
        "pr": _at(s, "pr", "url"),
        "errors": [_at(f, "message") for f in failures],
    }
    return json.loads(redact_secrets(json.dumps(body, default=str)))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
