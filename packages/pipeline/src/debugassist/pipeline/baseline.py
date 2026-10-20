"""Baseline arm (ROADMAP-100 090): a plain tool-using agent on the same issue, with no plan around it.

    debugassist baseline <issue> [--llm live|mock]      # or `debugassist eval run --configs baseline`

What the pipeline adds — triage, the pre-collected evidence bundle, decisions, subagents, the grounding check, the
reproduce-then-fix contract, validation, the ship gate — the baseline does without. It keeps what any agent would be
given: the same intake (the issue as discovered), a worktree at the shipped release with dependencies installed,
the evidence tools (MCP servers) its agent type grants the RCA step, and file and shell tools in the worktree. One
agent investigates, edits, runs whatever it likes and submits a root cause; its turns, tool calls and budget are
the RCA's and the fix's added together.

The one thing it may ask for is the hand-off every engineer has: when it names a root cause in another target repo,
the same deterministic `crossrepo.retarget` the pipeline uses moves the worktree there, and the agent goes on once,
told what it found. Its result is written in the pipeline's run format (rca.output, fix_attempts[0].diff, ship), so
`evals.score` grades it unchanged — hidden tests against its final worktree included. It is never validated and
never ships: `validated` is always false and the outcome is draft_pr (a change) or rca_only (none).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from debugassist.core import untrusted
from debugassist.llm.spec import LLMNodeSpec, LLMResult
from debugassist.llm.workspace_tools import build_workspace_tools, changed_files
from debugassist.pipeline import crossrepo, nodes
from debugassist.pipeline.deps import Deps
from debugassist.pipeline.graph import wrap
from debugassist.pipeline.state import (
    RCA,
    Category,
    CodeLocation,
    FixAttempt,
    Issue,
    RCAOutput,
    RunState,
    Ship,
)

NODE = "baseline"


class BaselineOutput(BaseModel):
    summary: str = Field(description="2-3 sentences: what is wrong and what you changed")
    category: Category
    root_cause: str = Field(description="the defect and the mechanism that turns it into the symptom")
    location: CodeLocation
    fix_direction: str = Field(description="what a correct fix does")
    changed_code: bool = Field(description="whether you left a fix in the worktree")
    tests_added: list[str] = Field(default_factory=list[str], description="test files you added or changed")


def spec(deps: Deps) -> LLMNodeSpec:
    """The RCA's and the fix's limits added together; the RCA's evidence tools."""
    rca, fix = deps.agent_type["nodes"]["classify_rca"], deps.agent_type["nodes"]["fix"]
    return LLMNodeSpec(
        node=NODE,
        system_prompt=nodes.load_prompt("baseline_system.md"),
        reasoning_effort=rca.get("reasoning_effort", "high"),
        max_turns=int(rca.get("max_turns", 20)) + int(fix.get("max_turns", 20)),
        max_tool_calls=int(rca.get("max_tool_calls", 30)) + int(fix.get("max_tool_calls", 40)),
        max_budget_usd=float(rca.get("max_budget_usd", 0.5)) + float(fix.get("max_budget_usd", 1.0)),
        max_wall_s=1800,
        mcp_servers=list(rca.get("mcp_servers", [])),
    )


def prompt(issue: Issue, test: str, lint: str | None) -> str:
    """The issue as intake recorded it, and how to work in the repository. Nothing pre-collected."""
    event = json.dumps(issue.latest_event, default=str)[:3000] if issue.latest_event else ""
    return (
        f"Issue {issue.id} ({issue.source}): {issue.kind} in app '{issue.app}' on {issue.platform}, "
        f"{issue.events} events, versions {issue.first_version}→{issue.last_version}.\n"
        + untrusted.fence("issue title", issue.title)
        + "\n"
        + (untrusted.fence("latest event", event) + "\n" if event else "")
        + (
            untrusted.fence("user report", json.dumps(issue.report, default=str)[:1500]) + "\n"
            if issue.report
            else ""
        )
        + f"\nYour worktree is {issue.repo} at release v{issue.last_version} (dependencies installed); the "
        f"component is '{issue.component}' ({issue.language}). Its tests: `{test}`"
        + (f"; CI also runs `{lint}`" if lint else "")
        + ".\nThe other MiniRide repository can be searched with the code tools. Find the root cause, fix it in "
        "this worktree with a test that would have caught it, and submit. If the root cause is in another "
        "repository, submit with the location there and changed_code false: you will continue in that "
        "repository's worktree."
    )


def _rca_output(out: BaselineOutput) -> RCAOutput:
    return RCAOutput(
        summary=out.summary,
        category=out.category,
        root_cause=out.root_cause,
        location=out.location,
        claims=[],
        timeline=[],
        reproduction="",
        fix_direction=out.fix_direction,
    )


async def investigate_and_fix(state: RunState, deps: Deps) -> dict[str, Any]:
    issue = state.issue
    assert issue
    sb = nodes.sandbox_for(state)
    sb.create(f"v{issue.last_version}", nodes.bot_branch(issue, deps))
    results: list[LLMResult] = []
    costs = dict(state.costs)
    out: BaselineOutput | None = None
    for session in (1, 2):  # a second session only after a hand-off to another repository
        comp = nodes.component_cfg(state, sb.worktree)
        res = sb.install(str(comp["setup"]), workdir=issue.component)
        if res.exit_code:
            raise RuntimeError(f"dependency install failed: {res.output[-1500:]}")
        task = prompt(issue, str(comp.get("test", "")), comp.get("lint"))
        if out is not None:
            task += "\n\nYour investigation so far (you handed off to this repository):\n" + untrusted.fence(
                "your earlier result", out.model_dump_json()
            )
        base = f"v{issue.last_version}"
        r: LLMResult = await deps.runner(nodes.apply_diff(sb)).run(
            spec(deps),
            task,
            BaselineOutput,
            tools=build_workspace_tools(sb, allow_edits=True, allow_commands=True, workdir=issue.component),
            mcp_env=nodes.code_repos_env(state),
            diff_fn=lambda bsb=sb, b=base: bsb.diff(b),
        )
        nodes.stop_if_out_of_quota(r, state, NODE)
        results.append(r)
        costs[f"{NODE}_{session}"] = r.cost_usd
        if not r.output:
            break
        out = BaselineOutput.model_validate(r.output)
        if session == 2 or sb.workspace.dirty():
            break
        rca = RCA(output=_rca_output(out))
        moved = crossrepo.retarget(state.model_copy(update={"rca": rca}), deps, nodes.bot_branch(issue, deps))
        if not moved:
            break
        state = state.model_copy(update=moved)
        issue = state.issue
        assert issue
        sb = nodes.sandbox_for(state)
    if out is None:
        raise RuntimeError(f"baseline agent ended with status {results[-1].status if results else 'none'}")
    diff = sb.diff(f"v{issue.last_version}") if sb.workspace.dirty() else ""
    attempts = [FixAttempt(n=1, diff=diff, files=changed_files(diff))] if diff else []
    summary = nodes.llm_summary(results[-1]) | {
        "turns": sum(r.turns for r in results),
        "cost_usd": sum(r.cost_usd for r in results),
        "sessions": len(results),
    }
    return {
        # after a hand-off: the repository the agent moved to (unchanged otherwise)
        "issue": state.issue,
        "handoff": state.handoff,
        "agent_type": state.agent_type,
        "agent_type_reason": state.agent_type_reason,
        "rca": RCA(output=_rca_output(out), llm=summary),
        "fix_attempts": attempts,
        "ship": Ship(outcome="draft_pr" if diff else "rca_only", decision={"by": "baseline: changed or not"}),
        "costs": costs,
        "status": "done",
    }


async def run(state: RunState, deps: Deps, log: Callable[[str], None] = print) -> RunState:
    """Intake, then the one agent: through the pipeline's node wrapper, so state files, tracing and the run's
    values for the code tools are the same as a pipeline run's."""
    for name, fn in (("ingest", nodes.ingest), (NODE, investigate_and_fix)):
        update = await wrap(name, fn, deps, log)(state)
        state = state.model_copy(update=update)
        if state.status in ("failed", "duplicate", "stopped"):
            break
    return state
