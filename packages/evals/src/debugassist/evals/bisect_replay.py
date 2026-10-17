"""Replay the bisect proof (pipeline/bisect.py, DA_BISECT) on runs already made — no model, no new runs.

For each real case: a scratch checkout (as for the call-variation replay), and for every earlier run whose fix
validated, its reproduction test — the test file from the run's last fix cassette — run back through history
from the release. Each result is set beside the commit the run's RCA named as the cause. The cassettes and run
states live in .data/ (not committed); the output is written into the report directory.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from debugassist.core.policy import ROOT
from debugassist.evals.variants_replay import CASSETTES, scratch_checkout, sh
from debugassist.pipeline import bisect
from debugassist.pipeline.nodes import repro_problem
from debugassist.pipeline.state import Issue
from debugassist.scenarios.real import cases, load_case, load_issue

RUNS = ROOT / ".data" / "runs"
TIMEOUT = 120  # seconds per test run on an old commit


def _obj(v: Any) -> dict[str, Any]:
    return cast(dict[str, Any], v) if isinstance(v, dict) else {}


def replay(
    rows: list[dict[str, Any]], log: Callable[[str], None] = print, only: set[str] | None = None
) -> dict[str, Any]:
    """Every real case (or only those in `only`)."""
    out: list[dict[str, Any]] = []
    for cid in [c for c in cases() if not only or c in only]:
        gh = load_issue(load_case(cid).source)
        entry: dict[str, Any] = {"case": cid, "issue": gh.url, "runs": []}
        out.append(entry)
        wt, comp, err = scratch_checkout(gh)
        if err:
            entry["error"] = err
            continue
        tag = f"v{gh.checkout.version}"
        template = str(comp.get("test_one") or comp["test"] + " {file}")
        seen: set[str] = set()
        for r in rows:
            if r.get("bug") != cid or str(r.get("validated")) != "True":
                continue
            state_f = RUNS / str(r["run_id"]) / "state.json"
            cas = sorted(
                (CASSETTES / str(r["run_id"])).glob("fix*.json"), key=lambda f: (len(f.stem), f.stem)
            )
            if not state_f.is_file() or not cas:
                continue
            state = cast(dict[str, Any], json.loads(state_f.read_text()))
            fa = _obj((cast(list[Any], state.get("fix_attempts")) or [{}])[-1])
            test_file = str(_obj(fa.get("repro")).get("test_file") or "")
            diff = str(json.loads(cas[-1].read_text())["result"].get("diff") or "")
            if not test_file or not diff:
                continue
            sh(["git", "checkout", "-q", "-f", tag], wt)
            sh(["git", "reset", "-q", "--hard", tag], wt)
            ok = sh(
                ["git", "apply", f"--include={test_file}", "-"],
                wt,
                diff if diff.endswith("\n") else diff + "\n",
            )
            if ok.returncode or not (wt / test_file).is_file():
                entry["runs"].append(
                    {"run_id": r["run_id"], "arm": r.get("arm"), "result": "could not apply"}
                )
                continue
            key = (wt / test_file).read_text()
            if key in seen:  # the same test (e.g. a rerun): bisecting it again proves nothing new
                (wt / test_file).unlink()
                continue
            seen.add(key)
            issue = Issue.model_validate(state["issue"])
            cmd = template.format(file=test_file)

            def run(command: str, wt: Path = wt) -> tuple[int, str]:
                try:
                    p = subprocess.run(
                        shlex.split(command),
                        cwd=wt,
                        capture_output=True,
                        text=True,
                        timeout=TIMEOUT,
                        check=False,
                    )
                except subprocess.TimeoutExpired:
                    return 124, "timed out"  # judged like any run that did not reproduce: skipped
                return p.returncode, p.stdout + p.stderr

            def unrelated(code: int, output: str, cmd: str = cmd, issue: Issue = issue) -> bool:
                return code != 0 and repro_problem(cmd, code, output, issue) is not None

            found = bisect.prove_by_case(
                wt, tag, test_file, cmd, bisect.case_command(cmd, test_file), unrelated, run
            )
            (wt / test_file).unlink(missing_ok=True)
            suspect = cast(str | None, _obj(_obj(state.get("rca")).get("output")).get("suspect_commit"))
            entry["runs"].append(
                {
                    "run_id": r["run_id"],
                    "arm": r.get("arm"),
                    "seed": r.get("seed"),
                    "rca_suspect": suspect,
                    "agrees_with_rca": bisect.agrees(found, suspect),
                    **{
                        k: found.get(k)
                        for k in (
                            "result",
                            "good",
                            "first_bad",
                            "subject",
                            "steps",
                            "skipped",
                            "candidates",
                            "why",
                            "tags_tried",
                            "case",
                            "whole_file",
                            "by_case",
                        )
                    },
                }
            )
            log(f"{cid} {r.get('arm')} {r.get('seed')}: {found.get('result')} {found.get('first_bad') or ''}")
        sh(["git", "checkout", "-q", "-f", tag], wt)
    return {"cases": out}


def summary_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for c in data.get("cases", []):
        all_rs = c.get("runs", [])
        rs = [r for r in all_rs if r.get("result") != "could not apply"]
        found = [r for r in rs if r.get("result") == "found"]
        commits = sorted({str(r["first_bad"]) for r in found})
        rows.append(
            {
                "case": c["case"],
                "tests": len(rs),
                "not_applied": len(all_rs) - len(rs),
                "found": len(found),
                "commits": ", ".join(commits) or "—",
                "agree_with_rca": sum(1 for r in rs if r.get("agrees_with_rca") is True),
                "rca_named_another": sum(1 for r in rs if r.get("agrees_with_rca") is False),
                "other": ", ".join(sorted({str(r.get("result")) for r in rs if r.get("result") != "found"}))
                or "—",
            }
        )
    return rows
