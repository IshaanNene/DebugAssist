"""Extra checks after validation (all off by default): a second reproduction, call variations, bisect."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from debugassist.core import untrusted
from debugassist.core.ablation import second_repro_mode
from debugassist.integrations.sandbox import Sandbox
from debugassist.llm.spec import LLMNodeSpec
from debugassist.llm.workspace_tools import build_workspace_tools, is_test_path
from debugassist.pipeline import (
    bisect,
    budget,
    callvariants,
    release,
    skills,
    usages,
)
from debugassist.pipeline.deps import Deps
from debugassist.pipeline.nodes.common import llm_summary, load_prompt, repro_problem, stop_if_out_of_quota
from debugassist.pipeline.nodes.testing import (
    apply_diff,
    file_at_release,
    new_test_files,
    repro_cmd,
    revert_non_tests,
    run_test,
)
from debugassist.pipeline.state import (
    Issue,
    ReproOutput,
    RunState,
    TestRun,
)


def check_prompt(issue: Issue, comp: dict[str, Any], base: str, location: str, uses: str = "") -> str:
    """The independent check's task: the report and where the defect is — not the RCA's reproduction idea or fix
    direction, the fix, or the first test. With DA_SECOND_REPRO=callers, also how the code is used elsewhere."""
    return (
        f"Repository {issue.repo}, component dir '{issue.component}' ({issue.language}); commands run from there. "
        f"Release {base}.\n"
        + (f"The repository: {issue.about}.\n" if issue.about else "")
        + f"Component test command: `{comp['test']}`; tests live under `{comp.get('test_file_glob', 'test/')}`.\n"
        + untrusted.fence("issue title", issue.title)
        + "\n"
        + (
            untrusted.fence("user report", json.dumps(issue.report, default=str)[:3000]) + "\n"
            if issue.report
            else ""
        )
        + (
            untrusted.fence("latest event", json.dumps(issue.latest_event, default=str)[:1500]) + "\n"
            if issue.latest_event
            else ""
        )
        + f"\nThe defect is in {location}.\n"
        + (
            "\nHow this code is used elsewhere in the repository (its documentation, type stubs, tests, callers):\n"
            + untrusted.fence("repository usages", uses)
            + "\nA fix must keep these uses working as well as fix the report's example. Besides the report's case, "
            "cover the ways they call or rely on this code that the bug touches — how arguments are passed, the "
            "attributes and return values they use.\n"
            if uses
            else ""
        )
        + "Write the test, run it to see it fail, then submit."
    )


async def second_reproduction(
    state: RunState, deps: Deps, sb: Sandbox, comp: dict[str, Any], base: str
) -> tuple[TestRun | None, dict[str, Any], float]:
    """DA_SECOND_REPRO: a separate agent writes a test from the report alone, on the release, without the fix or
    any test the fixing agent wrote; the fix is then run against it. Returns (the run with the fix, or None when no
    valid second reproduction was written; a record; cost). Both runs happen in disposable checkouts of the
    release: the run's worktree is only read."""
    issue, rca = state.issue, state.rca
    assert issue and rca and rca.output
    loc = f"{rca.output.location.file} → {rca.output.location.function}"
    classes = release.classify_changes(sb.worktree, base)
    taken = {*classes.get("new_test", []), *classes.get("modified_test", [])}  # the fixing agent's tests
    rec: dict[str, Any] = {}
    cost = 0.0
    with release.release_checkout(sb, base) as rsb:  # the release: no fix, none of the fixing agent's tests
        cfg = budget.cap(dict(deps.agent_type["nodes"]["fix"]), deps)
        check_cfg: dict[str, Any] = {**cfg, "max_turns": min(15, int(cfg["max_turns"]))}
        node = "reproduce_check" + (f"_{len(state.fix_attempts)}" if len(state.fix_attempts) > 1 else "")
        skill_prompt, skill_tools = skills.for_node(deps.agent_type, "reproduce", issue)
        spec = LLMNodeSpec(
            node=node,
            system_prompt=load_prompt("reproduce_check_system.md") + skill_prompt,
            **check_cfg,
        )
        tools = (
            build_workspace_tools(
                rsb, allow_edits=True, allow_commands=True, editable=is_test_path, workdir=issue.component
            )
            + skill_tools
        )

        def check(out: dict[str, Any]) -> str | None:
            p = str(out.get("test_file", ""))
            if not is_test_path(p) or not (rsb.worktree / p).is_file():
                return f"{p} does not exist as a test file. Create it with write_file first."
            if p in taken or file_at_release(rsb, base, p) is not None:
                return f"{p} is already taken; write your test in a new file with another name."
            cmd = repro_cmd(issue, p)
            res = run_test(rsb, issue, cmd)
            return repro_problem(cmd, res.exit_code, res.output, issue)

        uses = ""
        if second_repro_mode() == "callers":
            names = usages.names_for(
                rsb.worktree, rca.output.location.function, usages.report_text(issue.report)
            )
            uses = usages.collect(rsb.worktree, names, exclude={rca.output.location.file})
            rec["usages"] = {"names": names, "chars": len(uses)}
        r = await deps.runner(apply_diff(rsb)).run(
            spec,
            check_prompt(issue, comp, base, loc, uses),
            ReproOutput,
            tools=tools,
            diff_fn=lambda: rsb.diff(base),
            validate_output=check,
        )
        stop_if_out_of_quota(r, state, "validate")
        cost = r.cost_usd
        rec["llm"] = llm_summary(r)
        revert_non_tests(rsb)  # source is read-only for the checker, whatever it ran
        written = [
            f
            for f in new_test_files(rsb)
            if f not in taken
            and file_at_release(rsb, base, f) is None
            and not (rsb.worktree / f).is_symlink()
        ]
        claimed = str((r.output or {}).get("test_file", ""))
        path = claimed if claimed in written else (written[-1] if written else None)
        if path is None:
            rec["result"] = "no second reproduction written; not checked"
            return None, rec, cost
        cmd = repro_cmd(issue, path)
        before = run_test(rsb, issue, cmd)
        rec.update(test_file=path, command=cmd, before_exit=before.exit_code)
        if problem := repro_problem(cmd, before.exit_code, before.output, issue):
            rec["result"] = (
                f"the second test does not reproduce the bug on the release; not checked: {problem[:300]}"
            )
            return None, rec, cost
        rec["test_source"] = (rsb.worktree / path).read_text()[:2500]
        second = release.patch(rsb.worktree, base, [path])
    # The fix's source change (not its tests) against the second test; a check, never part of the fix.
    with release.release_checkout(sb, base, classes.get("source", []), extra=second) as fsb:
        after = run_test(fsb, issue, cmd)
    rec.update(after_exit=after.exit_code, after_tail=after.output[-1500:] if after.exit_code else "")
    rec["result"] = "passes with the fix" if after.exit_code == 0 else "fails with the fix"
    run = TestRun(
        label="second reproduction, written without seeing the fix, with the fix",
        command=cmd,
        exit_code=after.exit_code,
        output_tail=after.output[-3000:],
    )
    return run, rec, cost


def python_for(comp: dict[str, Any]) -> str:
    """The component's Python interpreter, from its test command (e.g. `.venv/bin/python -m pytest`)."""
    first = str(comp.get("test", "")).split()[:1]
    if first and first[0].rsplit("/", 1)[-1].startswith("python"):
        return first[0]
    return "uv run --offline python" if str(comp.get("test", "")).startswith("uv run") else "python"


def call_variants_check(sb: Sandbox, issue: Issue, comp: dict[str, Any]) -> dict[str, Any]:
    """DA_CALL_VARIANTS: run each re-spelling of the report's calls with the fix; every one must print what the
    reported spelling prints. Returns a record: result pass / fail / unchecked, and the mismatches."""
    if issue.language != "python":
        return {"result": "unchecked", "why": f"not Python ({issue.language})"}
    code = callvariants.session(usages.report_text(issue.report))
    if not code:
        return {"result": "unchecked", "why": "no Python code in the report"}
    py = python_for(comp)
    probe = sb.worktree / (issue.component if issue.component != "." else "") / ".debugassist_variant.py"

    def run(program: str) -> str:
        probe.write_text(program)
        return sb.run(f"{py} {probe.name}", workdir=issue.component).output

    try:
        rec = callvariants.run_check(code, run)
    finally:
        probe.unlink(missing_ok=True)
    if rec["result"] == "fail":
        rec["note"] = (
            "Callers can make the same call these other ways, or inspect it; the fix must keep them working."
        )
    return rec


def prove_culprit(state: RunState, sb: Sandbox, issue: Issue, test_file: str, cmd: str) -> dict[str, Any]:
    """DA_BISECT: the validated reproduction test run back through history to the commit that introduced the bug,
    set beside the RCA's own suspect. Unit and integration tests only (an E2E spec needs a build per commit)."""

    def run(command: str) -> tuple[int, str]:
        res = run_test(sb, issue, command)
        return res.exit_code, res.output

    def unrelated(code: int, output: str) -> bool:  # failed, but not as a reproduction (syntax, time-out, …)
        return code != 0 and repro_problem(cmd, code, output, issue) is not None

    try:
        rel = test_file if issue.component == "." else test_file.removeprefix(f"{issue.component}/")
        found = bisect.prove_by_case(
            sb.worktree,
            f"v{issue.last_version}",
            test_file,
            cmd,
            bisect.case_command(cmd, rel),
            unrelated,
            run,
        )
    except (subprocess.CalledProcessError, OSError) as e:
        return {"result": "error", "why": str(e)[:300]}
    suspect = state.rca.output.suspect_commit if state.rca and state.rca.output else None
    return {**found, "rca_suspect": suspect, "agrees_with_rca": bisect.agrees(found, suspect)}
