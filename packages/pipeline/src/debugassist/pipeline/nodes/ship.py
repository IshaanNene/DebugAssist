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
    ShipReason,
)

ROUTED = ("infra", "device_os", "not_a_bug", "third_party_lib")


def skip_reason(skip: str) -> ShipReason:
    """The fix plan's skip text (fixplan.choose_strategy / choose_tier) as a typed reason."""
    if skip.startswith("needs a human"):
        return "needs_human"
    if skip.startswith("flag-only"):
        return "flag_config"
    return "repro_failed"  # "cannot be reproduced automatically", or no test tier applies


def explain(state: RunState, ship: Ship) -> str:
    """Why no PR, in words a maintainer reads: built from the typed reason, never from the outcome alone."""
    o = state.rca.output if state.rca else None
    text = {
        "not_our_code": "No fix proposed: the root cause is outside this repository's code"
        + (f" ({o.category.replace('_', ' ')})." if o else "."),
        "flag_config": "No code fix proposed: the feature flag's configuration is the defect, "
        "and the flag is the mitigation.",
        "no_fix": "No fix proposed: the analysis did not produce an actionable root cause and fix "
        "in this repository's code.",
        "repro_failed": "No fix proposed: the root cause appears to be in this repository's code, but no test "
        "reproduced the failure on the released version, so there is no proof that a change fixes it.",
        "no_source_change": "No fix proposed: a reproduction test fails on the release, but the change "
        "did not edit any source file.",
        "needs_human": "No fix proposed: this needs a maintainer's decision.",
    }.get(ship.reason or "", f"No pull request ({ship.outcome.replace('_', ' ')}).")
    if ship.outcome == "escalate" and ship.reason != "needs_human":
        text += " This needs a maintainer's decision."
    return text


async def ship_gate(state: RunState, deps: Deps) -> dict[str, Any]:
    rca, v = state.rca, state.validation
    if state.fix_plan and state.fix_plan.skip:
        skipped = skip_reason(state.fix_plan.skip)
        outcome: ShipOutcome = "escalate" if skipped == "needs_human" else "rca_only"
        return {"ship": Ship(outcome=outcome, reason=skipped, decision={"reason": state.fix_plan.skip})}
    if rca is None or not rca.actionable or not state.fix_attempts:
        cat = rca.output.category if rca and rca.output else None
        m = state.mitigation
        routed: ShipReason
        if cat == "flag_config" and m and m.action != "none":
            routed, reason = "flag_config", f"the flag's configuration is the defect: {m.detail}"
        elif cat in ROUTED:
            routed, reason = "not_our_code", f"not a code change in our repos ({cat}): reported and routed"
        else:
            routed, reason = "no_fix", "not actionable or no fix"
        return {"ship": Ship(outcome="rca_only", reason=routed, decision={"reason": reason})}
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
    why: ShipReason | None = None
    has_fix = fa.repro_verified and any(not is_test_path(f) for f in fa.files)
    if not has_fix:
        # No verified reproduction or no source change: nothing to put in a PR. D16's escalate stands.
        why = "repro_failed" if not fa.repro_verified else "no_source_change"
        outcome = "escalate" if outcome == "escalate" else "rca_only"
    elif outcome in ("escalate", "rca_only"):
        why = "needs_human"  # a proven fix that D16 held back
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
            reason=why,
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
