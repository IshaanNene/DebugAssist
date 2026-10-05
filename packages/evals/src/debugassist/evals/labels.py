"""Ground-truth labels for decisions, from the catalog (SPEC §12): which Clef decisions in a run were right.

Only decisions the catalog can judge are labelled:
  D01 priority (the catalog's priority) · D05 root-cause category · D11 roll back or not (a flag in the
  catalog mitigation) · D12 fix location (file + function) · D14 cheapest validation tier · D16 ship outcome.
Labels go to the ledger (`outcome_label`, source "catalog"): {"correct": bool, "expected": …, "got": …}.
"""

from __future__ import annotations

from typing import Any, cast

from debugassist.scenarios.catalog import Bug

PRIORITY_LEVELS = ["P4", "P3", "P2", "P1", "P0"]  # D01 score legend 0..4
TIER = {
    "tier_unit": "unit",
    "tier_integration": "integration",
    "tier_e2e": "e2e_env",
    "tier_none": "cannot_repro",
}


def _fn(name: str) -> str:
    return name.split(".")[-1]


def judge(
    decision_id: str,
    chosen: dict[str, Any],
    action: str | None,
    bug: Bug,
    params: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """{"correct", "expected", "got"} for a decision the catalog can judge; None otherwise."""
    d = decision_id[:3]
    if d == "D01":
        score = chosen.get("priority")
        if not isinstance(score, int | float):
            return None
        got = PRIORITY_LEVELS[max(0, min(4, round(float(score))))]
        return {"correct": got == bug.priority, "expected": bug.priority, "got": got}
    if d == "D05":
        got = chosen.get("category")
        return {"correct": got == bug.category, "expected": bug.category, "got": got}
    if d == "D11":
        m = bug.ground_truth.mitigation
        expected = isinstance(m, dict) and any(k in m for k in ("flag_rollback", "flag"))
        got = action == "rollback_flag"
        return {
            "correct": got == expected,
            "expected": "rollback" if expected else "keep",
            "got": "rollback" if got else "keep",
        }
    if d == "D12":
        gt = bug.ground_truth.location
        loc = str(chosen.get("location", ""))
        names = cast(dict[str, str], (params or {}).get("names") or {})  # opaque c1.. ids → "path::function"
        loc = names.get(loc, loc)
        if not gt.file or "::" not in loc:
            return (
                None
                if not gt.file
                else {"correct": False, "expected": f"{gt.file}::{gt.function}", "got": loc}
            )
        path, fn = loc.split("::", 1)
        return {
            "correct": path == gt.file and _fn(fn) == _fn(gt.function or ""),
            "expected": f"{gt.file}::{gt.function}",
            "got": loc,
        }
    if d == "D14":
        got = TIER.get(action or "", chosen.get("tier"))
        return {
            "correct": got == bug.validation.cheapest_tier,
            "expected": bug.validation.cheapest_tier,
            "got": got,
        }
    if d == "D16":
        got = action
        ok = (
            got in ("open_pr", "draft_pr")
            if bug.expected_outcome == "pr"
            else got in ("rca_only", "escalate")
        )
        return {"correct": ok, "expected": bug.expected_outcome, "got": got}
    return None


def d12_names(questions: dict[str, Any]) -> dict[str, str]:
    """Recover D12's opaque candidate ids (c1, c2, …) → "path::function" from the rendered question."""
    names: dict[str, str] = {}
    for q in questions.values():
        crit = cast(dict[str, Any], q).get("criteria") if isinstance(q, dict) else None
        if isinstance(crit, dict):
            for key, desc in cast(dict[str, Any], crit).items():
                head = str(desc).split(": ", 1)[0]  # "path::function: signature (line n) — reasons"
                if "::" in head:
                    names[str(key)] = head
    return names


async def label_run(ledger: Any, run_id: str, bug: Bug) -> int:
    """Label this run's decisions in the ledger; returns how many were labelled."""
    n = 0
    for r in await ledger.list(run_id=run_id):
        if r.parent_id:
            continue  # second opinions are judged through their parent
        verdict = judge(
            r.decision_id, dict(r.chosen or {}), r.action, bug, {"names": d12_names(dict(r.questions or {}))}
        )
        if verdict is not None:
            await ledger.label(r.id, {**verdict, "bug": bug.id}, source="catalog")
            n += 1
    return n
