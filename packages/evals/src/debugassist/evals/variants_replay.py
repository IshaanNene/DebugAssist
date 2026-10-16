"""Replay the call-variation check (pipeline/callvariants.py) on fixes already made — no model, no new runs.

For each real case whose report has calls to re-spell: a scratch checkout at the release, set up with the repo's
own setup command; then the check on the release, on the upstream fix (fetched from GitHub — the agent's checkout
never contains it), and on the last fix of every earlier run of that case (its diff from the run's cassette, test
files and binaries left out). Each fix's verdict is set against what upstream's regression test said about it.

The cassettes live in .data/ (not committed), so this replays only where those runs were made; its output is
written into the report directory and rendered by `debugassist eval report`.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import yaml

from debugassist.core.policy import ROOT
from debugassist.pipeline import callvariants as cv
from debugassist.pipeline import usages
from debugassist.scenarios.real import cases, load_case, load_issue

SCRATCH = ROOT / ".data" / "variants-replay"
CASSETTES = ROOT / ".data" / "cassettes"
_SKIP = [
    "--exclude=tests/*",
    "--exclude=test/*",
    "--exclude=*/tests/*",
    "--exclude=*.pyc",
    "--exclude=.coverage",
]


def _sh(cmd: list[str] | str, cwd: Path, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=cwd, shell=isinstance(cmd, str), capture_output=True, text=True, input=stdin, check=False
    )


def _check(wt: Path, py: str, code: str) -> dict[str, Any]:
    """The check as validate runs it, in the scratch checkout."""
    probe = wt / ".debugassist_variant.py"

    def run(program: str) -> str:
        probe.write_text(program)
        return _sh([py, probe.name], wt).stdout

    try:
        rec = cv.run_check(code, run)
    finally:
        probe.unlink(missing_ok=True)
    return {
        "verdict": rec["result"],
        "spellings": rec.get("checked", 0),
        "mismatch": rec.get("mismatches", [])[:1],
    }


def replay(rows: list[dict[str, Any]], log: Callable[[str], None] = print) -> dict[str, Any]:
    """rows: result rows (results.csv of a report). Returns {"cases": [...]}."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    out: list[dict[str, Any]] = []
    for cid in cases():
        case = load_case(cid)
        issue = load_issue(case.source)
        code = cv.session(usages.report_text({"body": issue.body})) or ""
        calls = (
            [b.call for b, _ in cv.variants(code)] + [a.call for a in cv.attribute_probes(code)]
            if code
            else []
        )
        entry: dict[str, Any] = {"case": cid, "issue": issue.url, "calls": calls, "fixes": []}
        out.append(entry)
        if not calls:
            log(f"{cid}: nothing to re-spell")
            continue
        comp = yaml.safe_load(issue.checkout.config)["components"]["."]
        tag = f"v{issue.checkout.version}"
        wt = SCRATCH / issue.repo
        if not wt.exists():
            _sh(["git", "clone", "-q", str(ROOT / "targets" / issue.repo), str(wt)], SCRATCH)
            _sh(["git", "checkout", "-q", tag], wt)
            if (r := _sh(str(comp["setup"]), wt)).returncode:
                entry["error"] = f"setup failed: {r.stderr[-300:]}"
                continue
        py = str(comp["test"]).split()[0]

        def reset(wt: Path = wt, tag: str = tag) -> None:
            _sh(["git", "checkout", "-q", "-f", tag], wt)
            _sh(["git", "clean", "-qfd", "-e", ".venv"], wt)

        def apply(diff: str, wt: Path = wt) -> bool:
            return (
                _sh(
                    ["git", "apply", *_SKIP, "-"], wt, diff if diff.endswith("\n") else diff + "\n"
                ).returncode
                == 0
            )

        reset()
        entry["release"] = _check(wt, py, code)
        sha = case.upstream["fix_commit"]
        _sh(["git", "fetch", "-q", f"https://github.com/{issue.gh_repo}.git", sha], wt)
        up = _sh(["git", "diff", tag, "FETCH_HEAD", "--", ".", ":!tests", ":!test"], wt).stdout
        reset()
        entry["upstream"] = _check(wt, py, code) if up and apply(up) else {"verdict": "could not apply"}
        for r in rows:
            if r.get("bug") != cid or str(r.get("hidden_tests")) not in {"True", "False"}:
                continue
            cas = sorted(
                (CASSETTES / str(r["run_id"])).glob("fix*.json"), key=lambda f: (len(f.stem), f.stem)
            )
            if not cas:
                continue
            reset()
            diff = str(json.loads(cas[-1].read_text())["result"].get("diff") or "")
            res = _check(wt, py, code) if diff and apply(diff) else {"verdict": "could not apply"}
            entry["fixes"].append(
                {
                    "run_id": r["run_id"],
                    "arm": r.get("arm"),
                    "seed": r.get("seed"),
                    "upstream_test": str(r["hidden_tests"]) == "True",
                    **res,
                }
            )
        reset()
        log(
            f"{cid}: upstream fix {entry['upstream']['verdict']}, {len(entry['fixes'])} earlier fixes replayed"
        )
    return {"cases": out}


def summary_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Per case: the upstream fix's verdict and how the check agreed with upstream's test on earlier fixes."""
    rows: list[dict[str, Any]] = []
    for c in data.get("cases", []):
        fx = [f for f in c.get("fixes", []) if f.get("verdict") in {"pass", "fail"}]

        def n(test: bool, verdict: str, fx: list[dict[str, Any]] = fx) -> int:
            return sum(1 for f in fx if f["upstream_test"] is test and f["verdict"] == verdict)

        rows.append(
            {
                "case": c["case"],
                "calls": len(c.get("calls", [])),
                "upstream_fix": cast(dict[str, Any], c.get("upstream") or {}).get("verdict", "—"),
                "fixes": len(fx),
                "test_pass_check_pass": n(True, "pass"),
                "test_fail_check_fail": n(False, "fail"),
                "test_pass_check_fail": n(True, "fail"),
                "test_fail_check_pass": n(False, "pass"),
            }
        )
    return rows
