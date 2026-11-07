"""Pre-registered arms (ROADMAP-100 083): thresholds stated before an arm runs, checked by the report."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel

from debugassist.core.policy import ROOT
from debugassist.evals.score import fix_success
from debugassist.evals.stats import mcnemar, rate_with_interval

ARMS = ROOT / "evals" / "arms"
Metric = Literal["rca_exact", "rca_exact_or_directional", "category_ok", "validated", "hidden_tests_pass"]
PRED: dict[str, Callable[[dict[str, Any]], bool | None]] = {
    "rca_exact": lambda r: r.get("rca") == "exact",
    "rca_exact_or_directional": lambda r: r.get("rca") in ("exact", "directional"),
    "category_ok": lambda r: bool(r.get("category_ok")),
    "validated": fix_success,  # only where the catalog expects a fix (scorer change of 2026-11-07)
    "hidden_tests_pass": lambda r: None if r.get("hidden_tests") is None else bool(r["hidden_tests"]),
}


class Check(BaseModel):
    metric: Metric
    at_least: float


class Comparison(BaseModel):
    """A paired claim: this arm against another arm (or the no-model control) on the same (bug, seed) runs."""

    metric: Metric
    versus: (
        str  # another arm's prefix, or "control": the no-model localization control on this arm's own runs
    )
    expect: Literal["better", "no_difference"]
    alpha: float = 0.05


class Arm(BaseModel):
    arm: str
    registered: datetime
    hypothesis: str
    checks: list[Check] = []
    comparisons: list[Comparison] = []


def load(arms: Path = ARMS) -> list[Arm]:
    return [Arm.model_validate(yaml.safe_load(f.read_text())) for f in sorted(arms.glob("*.yaml"))]


def _started(row: dict[str, Any]) -> datetime | None:
    try:
        return datetime.strptime(str(row.get("run_id", ""))[:15], "%Y%m%d-%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def evaluate(arms: list[Arm], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for arm in arms:
        mine = [r for r in rows if "rca" in r and str(r.get("arm", "")).startswith(arm.arm)]
        starts = [t for r in mine if (t := _started(r)) is not None]
        registered = arm.registered if arm.registered.tzinfo else arm.registered.replace(tzinfo=UTC)
        before = bool(starts) and registered <= min(starts)
        for c in arm.checks:
            values = [v for r in mine if (v := PRED[c.metric](r)) is not None]
            k, n = sum(values), len(values)
            out.append(
                {
                    "arm": arm.arm,
                    "metric": c.metric,
                    "threshold": c.at_least,
                    "observed": rate_with_interval(k, n),
                    "verdict": "no runs yet" if n == 0 else "met" if k / n >= c.at_least else "not met",
                    "pre_registered": "yes" if before else "no runs yet" if not starts else "no",
                }
            )
    return out


def _key(r: dict[str, Any]) -> tuple[str, int]:
    return (str(r.get("bug")), int(r.get("seed") or 0))


def compare(arms: list[Arm], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each registered comparison: discordant pairs and an exact McNemar test (stats.mcnemar)."""
    out: list[dict[str, Any]] = []
    for arm in arms:
        mine = {_key(r): r for r in rows if "rca" in r and str(r.get("arm", "")).startswith(arm.arm)}
        for c in arm.comparisons:
            pred = PRED[c.metric]
            pairs: list[tuple[bool, bool]] = []
            if c.versus == "control":
                if c.metric not in ("rca_exact", "rca_exact_or_directional"):
                    raise ValueError(f"{arm.arm}: the control only localizes; compare it on rca_* metrics")
                ok = ("exact",) if c.metric == "rca_exact" else ("exact", "directional")
                for r in mine.values():
                    if r.get("control_rca") is not None and (a := pred(r)) is not None:
                        pairs.append((a, r["control_rca"] in ok))
            else:
                theirs = {
                    _key(r): r for r in rows if "rca" in r and str(r.get("arm", "")).startswith(c.versus)
                }
                for k in sorted(set(mine) & set(theirs)):
                    a, b = pred(mine[k]), pred(theirs[k])
                    if a is not None and b is not None:
                        pairs.append((a, b))
            only_a = sum(1 for a, b in pairs if a and not b)
            only_b = sum(1 for a, b in pairs if b and not a)
            p = mcnemar(only_a, only_b)
            if not pairs:
                verdict = "no runs yet"
            elif c.expect == "better":
                verdict = "met" if p < c.alpha and only_a > only_b else "not met"
            elif p >= c.alpha:
                verdict = "met (no evidence of a difference)"
            else:
                verdict = f"not met: {arm.arm if only_a > only_b else c.versus} better"
            out.append(
                {
                    "arm": arm.arm,
                    "metric": c.metric,
                    "versus": c.versus,
                    "expect": c.expect,
                    "pairs": len(pairs),
                    "only_arm": only_a,
                    "only_versus": only_b,
                    "p": round(p, 4),
                    "verdict": verdict,
                }
            )
    return out
