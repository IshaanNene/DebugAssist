"""N6 validate: failing-before / passing-after proof, the suite and CI checks; D15 retry."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from debugassist.core.ablation import bisect_enabled, call_variants, second_repro
from debugassist.decisions.engine import RunContext
from debugassist.decisions.state import CompactState
from debugassist.llm.workspace_tools import is_test_path
from debugassist.pipeline import (
    release,
)
from debugassist.pipeline.deps import Deps
from debugassist.pipeline.nodes.checks import call_variants_check, prove_culprit, second_reproduction
from debugassist.pipeline.nodes.common import component_cfg, pipeline_yaml, repro_problem, sandbox_for
from debugassist.pipeline.nodes.testing import run_test
from debugassist.pipeline.state import (
    AttemptRecord,
    RunState,
    TestRun,
    Validation,
)


async def validate(state: RunState, deps: Deps) -> dict[str, Any]:
    """Failing-before / passing-after proof on the reproduction test, plus the full component suite."""
    issue = state.issue
    assert issue and state.fix_attempts
    sb = sandbox_for(state)
    comp = component_cfg(state, sb.worktree)
    fa = state.fix_attempts[-1]
    v = state.validation or Validation()
    record: dict[str, Any] = {"attempt": fa.n, "tier": fa.tier, "tiers_tried": fa.tiers_tried}
    base = f"v{issue.last_version}"
    # What this proof ran and with which config (ROADMAP-100 015): a reviewer, or a later run, can tell whether
    # two validations are comparable without re-reading the harness.
    record["harness"] = {
        "config_sha256": hashlib.sha256(
            json.dumps(pipeline_yaml(sb.worktree, issue), sort_keys=True, default=str).encode()
        ).hexdigest()[:16],
        "from": base,
        "commands": {k: str(comp[k]) for k in ("setup", "test", "lint") if comp.get(k)}
        | ({"reproduction": str(fa.repro_run["command"])} if (fa.repro_run or {}).get("command") else {}),
    }
    src = [f for f in fa.files if not is_test_path(f)]
    if not fa.repro_verified or not fa.repro:
        record.update(result="no reproduction test that fails on the release", repro_run=fa.repro_run)
    elif not src:
        record.update(result="no source change")
    else:
        cmd = str(fa.repro_run["command"])
        # Against the release tag in disposable checkouts (P3-16): the worktree keeps the fix whatever happens
        # here, and a validate resumed after the fix was committed proves the same thing.
        classes = release.classify_changes(sb.worktree, base)
        v.changes, v.protected = classes, release.flagged(sb.worktree, base, classes)
        record.update(changes=classes, **({"protected": v.protected} if v.protected else {}))
        # Failing-before: the release with the reproduction test as written.
        with release.release_checkout(sb, base, [fa.repro.test_file]) as rsb:
            before = run_test(rsb, issue, cmd)
        # Passing-after and the suite: the source change and the new tests only; pre-existing tests, the
        # harness and test-runner config, CI and lockfiles as in the release (P2-8), so a test edited to pass
        # or a skipped suite proves nothing. The reproduction test is part of the proof wherever it lives.
        proof = sorted({*release.proof_paths(classes), fa.repro.test_file})
        with release.release_checkout(sb, base, proof) as psb:
            after = run_test(psb, issue, cmd)
            suite = psb.run(str(comp["test"]), workdir=issue.component)
        v.passing_after = TestRun(
            label=f"reproduction test ({fa.tier}) with the fix",
            command=cmd,
            exit_code=after.exit_code,
            output_tail=after.output[-3000:],
        )
        v.failing_before = TestRun(
            label=f"reproduction test ({fa.tier}) on the release (expected to fail)",
            command=cmd,
            exit_code=before.exit_code,
            output_tail=before.output[-3000:],
        )
        if before_problem := repro_problem(cmd, before.exit_code, before.output, issue):
            record.update(failing_before_problem=before_problem[:600])
        v.suite = TestRun(
            label="full component suite with the fix (pre-existing tests as in the release)",
            command=str(comp["test"]),
            exit_code=suite.exit_code,
            output_tail=suite.output[-3000:],
        )
        if comp.get("lint"):
            static = sb.run(str(comp["lint"]), workdir=issue.component)
            v.static = TestRun(
                label="repository CI checks (lint, typecheck)",
                command=str(comp["lint"]),
                exit_code=static.exit_code,
                output_tail=static.output[-3000:],
            )
            record.update(
                static_exit=static.exit_code, static_tail=static.output[-1500:] if static.exit_code else ""
            )
        record.update(
            failing_before_exit=before.exit_code,
            passing_after_exit=after.exit_code,
            suite_exit=suite.exit_code,
            suite_tail=suite.output[-1500:] if suite.exit_code else "",
            after_tail=after.output[-1500:] if after.exit_code else "",
        )
    v.passed = bool(
        v.failing_before
        and v.failing_before.exit_code != 0
        and v.passing_after
        and v.passing_after.exit_code == 0
        and v.suite
        and v.suite.exit_code == 0
        and record.get("suite_exit") == 0
        and "failing_before_problem" not in record
        and (v.static is None or v.static.exit_code == 0)
    )
    costs = dict(state.costs)
    v.independent = None
    if v.passed and second_repro() and fa.tier != "e2e_env":
        run, rec, cost = await second_reproduction(state, deps, sb, comp, base)
        node = "reproduce_check" + (f"_{fa.n}" if fa.n > 1 else "")
        costs[node] = costs.get(node, 0.0) + cost
        record["second_reproduction"] = rec
        v.independent = run
        v.passed = run is None or run.exit_code == 0  # no valid second test: the fix is not held to one
    if v.passed and call_variants():
        record["call_variants"] = call_variants_check(sb, issue, comp)
        v.passed = record["call_variants"]["result"] != "fail"
    v.attempts.append(AttemptRecord.model_validate(record))
    out: dict[str, Any] = {"validation": v, "costs": costs}
    if v.passed and bisect_enabled() and fa.tier != "e2e_env" and fa.repro:
        out["bisect"] = prove_culprit(state, sb, issue, fa.repro.test_file, str(fa.repro_run["command"]))
    return out


async def decide_retry(state: RunState, deps: Deps) -> bool:
    """D15 inside the fixed attempt cap."""
    v = state.validation
    validation: dict[str, Any] = deps.agent_type.get("validation") or {}
    cap = int(validation.get("max_attempts", 3))
    if v is None or v.passed or len(state.fix_attempts) >= cap:
        return False
    if (
        v.attempts[-1].result is not None
    ):  # no reproduction or no change: always worth another attempt within the cap
        return True
    cs = (
        CompactState()
        .add("last_attempt", v.attempts[-1].model_dump(exclude_none=True), priority=0)
        .add("attempts_so_far", len(state.fix_attempts), priority=1)
    )
    d15 = await deps.engine.decide("D15", cs, ctx=RunContext(run_id=state.run_id, issue_id=state.issue_ref))
    return d15.action == "retry"
