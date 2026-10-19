"""N7 ship_gate: the D16 outcome, the scope check, the ready-PR policy."""

from __future__ import annotations

from typing import Any

from debugassist.decisions.engine import RunContext
from debugassist.decisions.state import CompactState
from debugassist.llm.workspace_tools import is_test_path
from debugassist.pipeline.deps import Deps
from debugassist.pipeline.state import (
    Issue,
    RunState,
    Ship,
    ShipOutcome,
)


async def ship_gate(state: RunState, deps: Deps) -> dict[str, Any]:
    rca, v = state.rca, state.validation
    if state.fix_plan and state.fix_plan.skip:
        outcome: ShipOutcome = "escalate" if state.fix_plan.skip.startswith("needs a human") else "rca_only"
        return {"ship": Ship(outcome=outcome, decision={"reason": state.fix_plan.skip})}
    if rca is None or not rca.actionable or not state.fix_attempts:
        cat = rca.output.category if rca and rca.output else None
        m = state.mitigation
        if cat == "flag_config" and m and m.action != "none":
            reason = f"the flag's configuration is the defect: {m.detail}"
        elif cat in ("infra", "device_os", "not_a_bug", "third_party_lib"):
            reason = f"not a code change in our repos ({cat}): reported and routed"
        else:
            reason = "not actionable or no fix"
        return {"ship": Ship(outcome="rca_only", decision={"reason": reason})}
    fa = state.fix_attempts[-1]
    cs = (
        CompactState()
        .add(
            "rca",
            {
                "category": rca.output.category if rca.output else None,
                "claims": len(rca.output.claims) if rca.output else 0,
                "suspect_commit": rca.output.suspect_commit if rca.output else None,
            },
            priority=0,
        )
        .add(
            "validation",
            {
                "passed": v.passed if v else False,
                "failing_before_reproduced": bool(v and v.failing_before and v.failing_before.exit_code),
                "attempts": len(state.fix_attempts),
            },
            priority=0,
        )
        .add(
            "diff",
            {
                "files": fa.files,
                "lines": fa.diff.count("\n"),
                "risk": fa.output.risk if fa.output else "unknown",
            },
            priority=1,
        )
    )
    d16 = await deps.engine.decide("D16", cs, ctx=RunContext(run_id=state.run_id, issue_id=state.issue_ref))
    outcome: ShipOutcome = (
        d16.action if d16.action in ("open_pr", "draft_pr", "rca_only", "escalate") else "draft_pr"
    )
    scope_note = ""
    has_fix = fa.repro_verified and any(not is_test_path(f) for f in fa.files)
    if not has_fix:
        outcome = "rca_only"  # no verified reproduction or no source change: nothing to put in a PR
    elif not (v and v.passed) and outcome == "open_pr":
        outcome = "draft_pr"  # never a ready PR without validation proof
    elif outcome == "open_pr" and v and v.protected:
        outcome = "draft_pr"  # a pre-existing test, harness, CI or lockfile changed: a flagged draft (P2-8)
    elif outcome == "open_pr" and (outside := outside_plan(state)):
        outcome = (
            "draft_pr"  # the fix spread well past where the plan and the RCA put the defect (ROADMAP-100 017)
        )
        scope_note = (
            f"{len(outside)} changed source file(s) outside the planned location: {', '.join(outside[:5])}"
        )
    elif outcome == "open_pr" and not ready_pr_allowed(state, deps):
        outcome = "draft_pr"  # a repository the app is installed on, not ours: draft PRs only (ADR 0008)
    return {
        "ship": Ship(
            outcome=outcome,
            risk=float(d16.chosen.get("risk", 0)),
            decision={
                "p": d16.p,
                "band": d16.band,
                "chosen": d16.chosen,
                **({"scope": scope_note} if scope_note else {}),
            },
        ),  # pyright: ignore[reportArgumentType]
        "decisions": [*state.decisions, d16.ledger_id or ""],
    }


SCOPE_SLACK = 2  # changed source files allowed beyond the planned ones (a helper, a sibling module)


def outside_plan(state: RunState) -> list[str]:
    """Changed source files beyond the fix plan's focus and the RCA's location, when more than SCOPE_SLACK."""
    fa, rca, plan = state.fix_attempts[-1], state.rca, state.fix_plan
    planned = {f.split("::")[0].removeprefix("./") for f in (plan.focus if plan else [])}
    if rca and rca.output:
        planned.add(rca.output.location.file.removeprefix("./"))
    if not planned:
        return []
    outside = sorted(f for f in fa.files if not is_test_path(f) and f.removeprefix("./") not in planned)
    return outside if len(outside) > SCOPE_SLACK else []


def commit_trailer(issue: Issue) -> str:
    """Where the fix came from: a Vitals crash, a BugDrop report, or the GitHub issue (audit P3-19)."""
    if issue.app_issue is not None or issue.source == "github":
        return f"Fixes: {issue.url}"
    return f"{'BugDrop' if issue.source == 'bugdrop' else 'Vitals'}: {issue.id}"


def ready_pr_allowed(state: RunState, deps: Deps) -> bool:
    issue = state.issue
    return bool(issue and issue.app_issue is None and deps.gate.ready_pr_allowed(issue.gh_repo))
