"""Score one pipeline run against the catalog's ground truth (SPEC §12).

RCA: exact (file + function match), directional (same file or module), wrong; category; expected outcome.
Fix: validation passed; hidden tests pass on the agent's change (run in a copy of the worktree, so ground
truth never enters the agent's sandbox); similarity of the changed lines to the reference fix.
Time and cost: discovery → RCA, discovery → end of run, turns, LLM and Clef spend.
"""

from __future__ import annotations

import difflib
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from debugassist.core.policy import ROOT
from debugassist.integrations.sandbox import CommandResult, Sandbox
from debugassist.scenarios.catalog import Bug

RUNS = ROOT / ".data" / "runs"
EVAL_WORK = ROOT / ".data" / "evals"
SOURCE_SUFFIXES = (".ts", ".tsx", ".py", ".go")


def _obj(v: Any) -> dict[str, Any]:
    return cast(dict[str, Any], v) if isinstance(v, dict) else {}


def _norm_path(path: str, bug: Bug) -> str:
    p = path.strip().lstrip("./")
    comp = bug.component if bug.component not in (".", "miniride-client") else ""
    if (
        comp
        and not p.startswith(comp + "/")
        and bug.ground_truth.location.file
        and bug.ground_truth.location.file.startswith(comp + "/")
    ):
        p = f"{comp}/{p}"  # an agent may give the path relative to the component
    return p


def _fn(name: str | None) -> str:
    return (name or "").split(".")[-1].split("(")[0].strip()


def rca_verdict(output: dict[str, Any] | None, bug: Bug) -> str:
    """exact | directional | wrong | none (for code bugs); for not-our-bug cases see `score_run`."""
    if not output:
        return "none"
    gt = bug.ground_truth.location
    loc = _obj(output.get("location"))
    file = _norm_path(str(loc.get("file", "")), bug)
    if not gt.file:
        return "none"
    if file == gt.file and _fn(str(loc.get("function"))) == _fn(gt.function):
        return "exact"
    module = (gt.module or "").strip("/")
    if file == gt.file or (module and (file.startswith(module + "/") or f"/{module}/" in f"/{file}")):
        return "directional"
    return "wrong"


def outcome_ok(ship: str | None, bug: Bug) -> bool:
    if bug.expected_outcome == "pr":
        return ship in ("open_pr", "draft_pr")
    return ship in ("rca_only", "escalate")


def changed_lines(diff: str) -> list[str]:
    """+/- lines of source files only (tests and config excluded)."""
    out: list[str] = []
    keep = False
    for line in diff.splitlines():
        if line.startswith("diff --git"):
            path = line.split(" b/", 1)[-1]
            keep = path.endswith(SOURCE_SUFFIXES) and "test" not in path.lower()
            continue
        if keep and line[:1] in "+-" and not line.startswith(("+++", "---")):
            out.append(line[0] + line[1:].strip())
    return out


def diff_similarity(agent_diff: str, reference: str) -> float | None:
    a, b = changed_lines(agent_diff), changed_lines(reference)
    if not a or not b:
        return None
    return round(difflib.SequenceMatcher(None, a, b).ratio(), 3)


class EvalSandbox(Sandbox):
    """A copy of a run's worktree where the evaluator (never the agent) runs hidden tests."""

    def __init__(self, run_id: str, repo_path: Path, repo: str, language: str, path: Path) -> None:
        super().__init__(run_id, repo_path, repo, language)
        self._path = path

    @property
    def worktree(self) -> Path:  # pyright: ignore[reportIncompatibleVariableOverride]
        return self._path


def _hidden_cmd(language: str, rel: str) -> str:
    if language == "python":
        return f"uv run --offline pytest -q {rel}"
    if language == "go":
        pkg = "./" + rel.rsplit("/", 1)[0] if "/" in rel else "."
        return f"go test {pkg}"
    return f"pnpm exec vitest run {rel}"


def hidden_tests(run_id: str, bug: Bug, state: dict[str, Any]) -> dict[str, Any]:
    """Run the catalog's hidden tests against the agent's final worktree (in a copy)."""
    tests = bug.ground_truth.hidden_tests
    src = RUNS / run_id / "repo"
    if not tests or not src.is_dir():
        return {"ran": False, "reason": "no hidden tests" if not tests else "worktree gone"}
    work = EVAL_WORK / run_id / "repo"
    shutil.rmtree(work.parent, ignore_errors=True)
    work.parent.mkdir(parents=True)
    subprocess.run(["cp", "-a", str(src), str(work)], check=True)
    issue = _obj(state.get("issue"))
    results: list[dict[str, Any]] = []
    for t in tests:
        dest = work / t.dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(bug.path(t.src), dest)
        comp = t.dest.split("/", 1)[0] if bug.component != "miniride-client" and "/" in t.dest else "."
        rel = t.dest if comp == "." else t.dest.split("/", 1)[1]
        sb = EvalSandbox(run_id, ROOT / "targets" / t.repo, str(issue.get("gh_repo", "")), bug.language, work)
        res: CommandResult = sb.run(_hidden_cmd(bug.language, rel), workdir=comp, timeout=600)
        results.append({"test": t.dest, "exit_code": res.exit_code, "tail": res.output[-600:]})
    return {"ran": True, "passed": all(r["exit_code"] == 0 for r in results), "results": results}


def _ts(path: Path) -> datetime | None:
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone() if path.exists() else None


def timings(run_id: str, state: dict[str, Any]) -> dict[str, float | None]:
    """Seconds from discovery (issue opened) to the RCA and to the end of the run; pipeline time."""
    issue = _obj(state.get("issue"))
    opened = issue.get("opened_at")
    nodes = sorted((RUNS / run_id / "nodes").glob("*.json"))
    rca = next((n for n in nodes if n.stem.endswith("classify_rca")), None)
    end = nodes[-1] if nodes else None
    start = datetime.fromisoformat(str(opened)) if opened else None
    rca_t, end_t = (_ts(rca) if rca else None), (_ts(end) if end else None)
    return {
        "discovery_to_rca_s": round((rca_t - start).total_seconds(), 1) if start and rca_t else None,
        "discovery_to_end_s": round((end_t - start).total_seconds(), 1) if start and end_t else None,
        "pipeline_s": round(sum(_obj(state.get("timings_ms")).values()) / 1000, 1),
    }


def turns(state: dict[str, Any]) -> int:
    n = int(_obj(_obj(state.get("rca")).get("llm")).get("turns") or 0)
    for fa in cast(list[Any], state.get("fix_attempts") or []):
        for v in _obj(_obj(fa).get("llm")).values():
            n += int(_obj(v).get("turns") or 0)
    return n


def score_run(run_id: str, bug: Bug, clef_usd: float = 0.0, run_hidden: bool = True) -> dict[str, Any]:
    state = json.loads((RUNS / run_id / "state.json").read_text())
    rca = _obj(state.get("rca"))
    out = _obj(rca.get("output")) or None
    attempts = cast(list[Any], state.get("fix_attempts") or [])
    last = _obj(attempts[-1]) if attempts else {}
    validation = _obj(state.get("validation"))
    ship = _obj(state.get("ship")).get("outcome")
    verdict = rca_verdict(out, bug)
    category = (out or {}).get("category")
    grounding = [_obj(g).get("grounding") for g in cast(list[Any], rca.get("grounding") or [])]
    if bug.expected_outcome != "pr":  # not our bug: right if routed with the right category, no fix attempted
        verdict = (
            "exact"
            if category == bug.category and not attempts
            else ("directional" if category == bug.category else "wrong")
        )
    reference = bug.path(bug.ground_truth.fix).read_text() if bug.ground_truth.fix else ""
    hidden = (
        hidden_tests(run_id, bug, state)
        if run_hidden and attempts and bug.expected_outcome == "pr"
        else {"ran": False}
    )
    llm_usd = round(sum(_obj(state.get("costs")).values()), 5)
    return {
        "run_id": run_id,
        "bug": bug.id,
        "status": state.get("status"),
        "agent_type": state.get("agent_type"),
        "rca": verdict,
        "rca_location": f"{_obj((out or {}).get('location')).get('file')} → {_obj((out or {}).get('location')).get('function')}"
        if out
        else None,
        "category_ok": category == bug.category,
        "outcome": ship,
        "outcome_ok": outcome_ok(ship, bug),
        "validated": bool(validation.get("passed")),
        "tier": last.get("tier"),
        "hidden_tests": hidden.get("passed") if hidden.get("ran") else None,
        "diff_similarity": diff_similarity(str(last.get("diff", "")), reference) if reference else None,
        "claims": len((out or {}).get("claims") or []),
        "claims_unsupported": grounding.count("unsupported"),
        "claims_unverified": grounding.count("unverified"),
        "turns": turns(state),
        "llm_usd": llm_usd,
        "clef_usd": round(clef_usd, 5),
        "usd": round(llm_usd + clef_usd, 5),
        **timings(run_id, state),
        "hidden_detail": hidden.get("results"),
        "errors": (state.get("errors") or [])[:1],
    }
