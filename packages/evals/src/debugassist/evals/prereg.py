"""Pre-registered arms (ROADMAP-100 083): thresholds stated before an arm runs, checked by the report."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel

from debugassist.core.policy import ROOT
from debugassist.evals.stats import rate_with_interval

ARMS = ROOT / "evals" / "arms"
Metric = Literal["rca_exact", "rca_exact_or_directional", "category_ok", "validated", "hidden_tests_pass"]
PRED: dict[str, Callable[[dict[str, Any]], bool | None]] = {
    "rca_exact": lambda r: r.get("rca") == "exact",
    "rca_exact_or_directional": lambda r: r.get("rca") in ("exact", "directional"),
    "category_ok": lambda r: bool(r.get("category_ok")),
    "validated": lambda r: bool(r.get("validated")),
    "hidden_tests_pass": lambda r: None if r.get("hidden_tests") is None else bool(r["hidden_tests"]),
}


class Check(BaseModel):
    metric: Metric
    at_least: float


class Arm(BaseModel):
    arm: str
    registered: datetime
    hypothesis: str
    checks: list[Check]


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
