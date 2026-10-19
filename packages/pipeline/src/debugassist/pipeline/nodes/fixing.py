"""N5 fix: plan once, then reproduce (tests only) and fix, per attempt."""

from __future__ import annotations

import json
from typing import Any

from debugassist.core import untrusted
from debugassist.llm.spec import LLMNodeSpec
from debugassist.llm.workspace_tools import build_workspace_tools, changed_files, is_test_path
from debugassist.pipeline import (
    budget,
    e2e,
    fixplan,
    skills,
)
from debugassist.pipeline.deps import Deps
from debugassist.pipeline.nodes.common import (
    component_cfg,
    llm_summary,
    load_prompt,
    pipeline_yaml,
    repro_problem,
    sandbox_for,
    static_problem,
    stop_if_out_of_quota,
)
from debugassist.pipeline.nodes.testing import (
    apply_diff,
    e2e_tool,
    fix_contract_problem,
    new_test_files,
    repro_cmd,
    reset_to,
    revert_non_tests,
    run_test,
    tier_problem,
)
from debugassist.pipeline.state import (
    FixAttempt,
    FixOutput,
    ReproOutput,
    RunState,
    Tier,
)


async def fix(state: RunState, deps: Deps) -> dict[str, Any]:
    """Plan once (D12–D14), then two enforced phases per attempt: (1) reproduce — tests only, must fail on
    the release, climbing the tier ladder until a tier reproduces; (2) fix — make it pass."""
    issue, rca = state.issue, state.rca
    assert issue and rca and rca.output
    sb = sandbox_for(state)
    comp = component_cfg(state, sb.worktree)
    attempt = len(state.fix_attempts) + 1
    base = f"v{issue.last_version}"
    reset_to(sb, base)
    if attempt == 1:
        res = sb.install(str(comp["setup"]), workdir=issue.component)
        if res.exit_code:
            raise RuntimeError(f"dependency install failed: {res.output[-1500:]}")
    costs = dict(state.costs)
    decisions = list(state.decisions)
    plan = state.fix_plan
    if plan is None:
        plan, ledgers = await fixplan.plan(sb, state, deps, pipeline_yaml(sb.worktree, issue))
        decisions += ledgers
    if plan.skip:
        return {"fix_plan": plan, "decisions": decisions}
    o = rca.output
    cfg = budget.cap(dict(deps.agent_type["nodes"]["fix"]), deps)
    context = (
        f"Repository {issue.repo}, component dir '{issue.component}' ({issue.language}); commands run from there. Release {base}.\n"
        f"Component test command: `{comp['test']}`; tests live under `{comp.get('test_file_glob', 'test/')}`.\n"
        + (f"CI also runs `{comp['lint']}`; it must pass.\n" if comp.get("lint") else "")
        + "\n"
        f"Root cause: {o.root_cause}\nLocation: {o.location.file} → {o.location.function}"
        f"{f' (line {o.location.line})' if o.location.line else ''}\nReproduction idea: {o.reproduction}\n"
        f"Correct fix direction: {o.fix_direction}\n" + fixplan.prompt_section(plan)
    )
    if state.validation and state.validation.attempts:
        context += (
            "\nThe previous attempt failed validation:\n"
            + untrusted.fence(
                "validation output",
                json.dumps(state.validation.attempts[-1].model_dump(exclude_none=True), default=str)[:3000],
            )
            + "\nTry a different approach.\n"
        )
    fa = FixAttempt(n=attempt)

    # Phase 1: reproduce (only test files may be written), up the ladder from the last tier that worked
    last = next((a.tier for a in reversed(state.fix_attempts) if a.tier), None)
    ladder = plan.ladder[plan.ladder.index(last) :] if last in plan.ladder else plan.ladder
    repro_cfg: dict[str, Any] = {**cfg, "max_turns": min(15, int(cfg["max_turns"]))}
    for tier in ladder:
        reset_to(sb, base)
        guide = fixplan.TIER_GUIDE[tier]
        if tier == "e2e_env":
            e2e.write_helpers(sb, issue.component)
            guide += (
                f"\n{e2e.helper_doc()}\nThe user's captured environment:\n"
                f"{json.dumps(plan.captured_env, default=str)[:2000]}\n"
                "Existing specs to copy conventions from: "
                + ", ".join(sorted(p.name for p in (sb.worktree / issue.component / "e2e").glob("*.spec.ts")))
                + "\n"
            )
        node = f"reproduce_{tier}" + (f"_{attempt}" if attempt > 1 else "")
        skill_prompt, skill_tools = skills.for_node(deps.agent_type, "reproduce", issue)
        repro_spec = LLMNodeSpec(
            node=node, system_prompt=load_prompt("reproduce_system.md") + skill_prompt, **repro_cfg
        )
        tools = (
            build_workspace_tools(
                sb, allow_edits=True, allow_commands=True, editable=is_test_path, workdir=issue.component
            )
            + skill_tools
        )
        if tier == "e2e_env":
            tools.append(e2e_tool(sb, issue))
        feedback = ""

        def check_repro(out: dict[str, Any], bound_tier: Tier = tier) -> str | None:
            path = str(out.get("test_file", ""))
            if not is_test_path(path) or not (sb.worktree / path).is_file():
                return f"{path} does not exist as a test file. Create it with write_file first."
            if problem := tier_problem(bound_tier, issue, path):
                return problem
            cmd = repro_cmd(issue, path)
            res = run_test(sb, issue, cmd)
            if problem := repro_problem(cmd, res.exit_code, res.output, issue):
                return problem
            if problem := static_problem(sb, comp, issue.component):
                return f"the test reproduces the bug, but {problem}\nClean up the test file (e.g. unused imports)."
            return None

        tried: dict[str, Any] = {"tier": tier}
        for _ in range(2):
            r1 = await deps.runner(apply_diff(sb)).run(
                repro_spec,
                context + guide + feedback + "\nWrite the reproduction test, run it if you can, then submit.",
                ReproOutput,
                tools=tools,
                diff_fn=lambda: sb.diff(base),
                validate_output=check_repro,
            )
            stop_if_out_of_quota(r1, state, "fix")
            costs[node] = costs.get(node, 0.0) + r1.cost_usd
            fa.llm[node] = llm_summary(r1)
            revert_non_tests(sb)  # source is read-only while reproducing, whatever the agent ran
            out = (
                r1.output
                if r1.output and (sb.worktree / str(r1.output.get("test_file", ""))).is_file()
                else None
            )
            if out is None:
                # The model sometimes stops without submitting: trust the worktree, not its word.
                helper = e2e.HELPER_PATH if issue.component == "." else f"{issue.component}/{e2e.HELPER_PATH}"
                written = [f for f in new_test_files(sb) if f != helper]
                if not written:
                    feedback = (
                        "\nYou did not write a reproduction test. Create one with write_file, then submit."
                    )
                    continue
                out = {
                    "test_file": written[-1],
                    "asserts": "(inferred from the test file the agent wrote)",
                    "failure": "(not reported by the agent; see the verification run)",
                }
                fa.llm[node]["note"] = "no valid submission; using the test file found in the worktree"
            fa.repro = ReproOutput.model_validate(out)
            cmd = repro_cmd(issue, fa.repro.test_file)
            run = run_test(sb, issue, cmd)
            fa.repro_run = {"command": cmd, "exit_code": run.exit_code, "output_tail": run.output[-2500:]}
            problem = (
                tier_problem(tier, issue, fa.repro.test_file)
                or repro_problem(cmd, run.exit_code, run.output, issue)
                or static_problem(sb, comp, issue.component)
            )
            fa.repro_verified = (
                problem is None
                and is_test_path(fa.repro.test_file)
                and (sb.worktree / fa.repro.test_file).is_file()
            )
            if fa.repro_verified:
                break
            fa.llm[node]["rejected"] = (problem or "")[:300]
            feedback = f"\nYour previous test was not a reproduction: {problem} Write a test that fails for the reason in the root cause."
        tried["verified"] = fa.repro_verified
        if fa.repro_run:
            tried["exit_code"] = fa.repro_run.get("exit_code")
        fa.tiers_tried.append(tried)
        if fa.repro_verified:
            fa.tier = tier
            break
    if not fa.repro_verified:
        fa.diff = sb.diff(base)
        fa.files = changed_files(fa.diff)
        return {
            "fix_attempts": [*state.fix_attempts, fa],
            "costs": costs,
            "fix_plan": plan,
            "decisions": decisions,
        }

    # Phase 2: fix. The reproduction test may be repaired (e.g. it hangs once the bug is fixed), but every
    # check re-proves the contract: with only the source change reverted it still fails with the production
    # error, and with the change it passes. A test weakened to pass is therefore rejected.
    repro = fa.repro
    assert repro
    tools = build_workspace_tools(
        sb,
        allow_edits=True,
        allow_commands=True,
        editable=lambda p: not p.startswith(("src/vendor/", "vendor/")),
        workdir=issue.component,
    )
    if fa.tier == "e2e_env":
        tools.append(e2e_tool(sb, issue))
    skill_prompt, skill_tools = skills.for_node(deps.agent_type, "fix", issue)
    tools += skill_tools
    fix_spec = LLMNodeSpec(
        node=f"fix_{attempt}" if attempt > 1 else "fix",
        system_prompt=load_prompt("fix_system.md") + skill_prompt,
        **cfg,
    )
    how = (
        "run it with the run_e2e tool (E2E against a fresh build of your change)"
        if fa.tier == "e2e_env"
        else f"run with `{fa.repro_run['command']}`"
    )
    prompt = (
        context
        + f"\nReproduction test ({fa.tier}): `{repro.test_file}` — {how}; it currently fails:\n"
        + untrusted.fence("test output", fa.repro_run["output_tail"][-1500:])
        + "\n\nFix the bug so this test and the component suite pass, then submit."
    )

    def check_fix(out: dict[str, Any]) -> str | None:
        return fix_contract_problem(sb, issue, comp, base, str(fa.repro_run["command"]), repro.test_file)

    r2 = await deps.runner(apply_diff(sb)).run(
        fix_spec, prompt, FixOutput, tools=tools, diff_fn=lambda: sb.diff(base), validate_output=check_fix
    )
    stop_if_out_of_quota(r2, state, "fix")
    costs[fix_spec.node] = costs.get(fix_spec.node, 0.0) + r2.cost_usd
    fa.llm["fix"] = llm_summary(r2)
    fa.output = FixOutput.model_validate(r2.output) if r2.output else None
    fa.diff = sb.diff(base)
    fa.files = changed_files(fa.diff)
    return {
        "fix_attempts": [*state.fix_attempts, fa],
        "costs": costs,
        "fix_plan": plan,
        "decisions": decisions,
    }
