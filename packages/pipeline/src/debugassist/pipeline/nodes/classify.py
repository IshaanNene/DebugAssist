"""N3 classify_rca: the root cause (agent, subagents, grounding)."""

from __future__ import annotations

import json
from typing import Any

from debugassist.core import untrusted
from debugassist.core.ablation import ablated
from debugassist.decisions.engine import RunContext
from debugassist.decisions.state import CompactState
from debugassist.llm.spec import LLMNodeSpec, LLMResult
from debugassist.pipeline import (
    budget,
    crossrepo,
    profile,
    skills,
)
from debugassist.pipeline import rca as rca_mod
from debugassist.pipeline.deps import Deps
from debugassist.pipeline.nodes.common import (
    NON_ACTIONABLE,
    bot_branch,
    code_repos_env,
    evidence_bundle,
    llm_summary,
    load_prompt,
    source_label,
    stop_if_out_of_quota,
)
from debugassist.pipeline.state import (
    RCA,
    Issue,
    RCAOutput,
    RunState,
)


async def classify_rca(state: RunState, deps: Deps) -> dict[str, Any]:
    issue = state.issue
    assert issue
    frames: list[dict[str, Any]] = issue.latest_event.get("frames") or []
    flags: dict[str, Any] = next((e.data for e in state.evidence if e.kind == "flag_exposure"), None) or {}
    versions: dict[str, Any] = (
        next(
            (
                e.data
                for e in state.evidence
                if e.kind == "distribution" and e.data.get("dimension") == "version"
            ),
            None,
        )
        or {}
    )
    cs = (
        CompactState()
        .add(
            "issue",
            {"title": issue.title, "kind": issue.kind, "app": issue.app, "platform": issue.platform},
            priority=0,
        )
        .add(
            "stack",
            [
                f"{f['function']} ({f['file']}:{f.get('line')})"
                + ("" if f.get("in_app", True) else " [library]")
                for f in reversed(frames[-8:])
            ],
            priority=1,
        )
        .add("flag_exposure", flags.get("flags"), priority=2)
        .add(
            "versions",
            [
                {k: r[k] for k in ("value", "sessions", "affected_sessions")}
                for r in versions.get("values", [])
            ],
            priority=3,
        )
    )
    d5 = await deps.engine.decide("D05", cs, ctx=RunContext(run_id=state.run_id, issue_id=issue.id))
    actionable = not (d5.band and d5.band.value == "act" and d5.action in NON_ACTIONABLE)
    rca = RCA(
        category_decision={
            "chosen": d5.chosen,
            "p": d5.p,
            "band": d5.band,
            "action": d5.action,
            "backend": d5.backend,
        },
        actionable=actionable,
    )
    decisions = [*state.decisions, d5.ledger_id or ""]
    costs = dict(state.costs)
    env = code_repos_env(state)
    st = state.model_copy(update={"rca": rca})
    # D10: reasoning effort by difficulty. Non-actionable categories get a short, routed RCA.
    cfg = budget.cap(dict(deps.agent_type["nodes"]["classify_rca"]), deps)
    effort, rca.routing, d10 = await rca_mod.route_effort(st, deps)
    decisions.append(d10 or "")
    cfg["reasoning_effort"] = effort if actionable else "low"
    findings: list[dict[str, Any]] = []
    sub_results: list[LLMResult] = []
    if actionable:
        # D6: a short evidence loop before the agent; D7: specialised subagents in parallel.
        added, rca.evidence_rounds, d6 = await rca_mod.evidence_loop(st, deps)
        decisions += d6
        if added:
            st = st.model_copy(update={"evidence": [*st.evidence, *added]})
        findings, sub_results, d7 = await rca_mod.fan_out(st, deps, env)
        decisions += d7
        rca.subagents = findings
        for f in findings:
            costs[f"subagent_{f['id']}"] = float(f.get("cost_usd") or 0.0)
    skill_prompt, skill_tools = skills.for_node(deps.agent_type, "classify_rca", issue)
    spec = LLMNodeSpec(
        node="classify_rca",
        system_prompt=profile.for_issue(load_prompt("rca_system.md"), issue) + skill_prompt,
        **cfg,
    )
    prompt = rca_prompt(issue, evidence_bundle(st.evidence), rca_mod.findings_text(findings))
    monitor_ledgers: list[str] = []
    r = await deps.runner().run(
        spec,
        prompt,
        RCAOutput,
        tools=skill_tools or None,
        mcp_env=env,
        monitor=None if ablated("D08") else rca_mod.make_monitor(st, deps, monitor_ledgers),
    )
    decisions += monitor_ledgers
    stop_if_out_of_quota(r, state, "classify_rca")
    rca.llm = llm_summary(r)
    costs["classify_rca"] = r.cost_usd
    if r.status not in ("ok", "max_turns", "stalled", "timeout") or not r.output:
        raise RuntimeError(f"RCA agent ended with status {r.status}: {r.error or 'no result'}")
    output = RCAOutput.model_validate(r.output)
    # D9: every claim checked against the evidence it cites.
    lookup = rca_mod.evidence_lookup(st, [r, *sub_results])
    if ablated("D09"):  # no grounding check: every claim is kept as written
        rca.output, rca.grounding, rca.dropped_claims, d9 = output, [], [], []
    else:
        rca.output, rca.grounding, rca.dropped_claims, d9 = await rca_mod.ground_claims(
            st, deps, output, lookup
        )
    decisions += d9
    update: dict[str, Any] = {"rca": rca, "decisions": decisions, "costs": costs, "evidence": st.evidence}
    # P14: the root cause is in another target repo → the fix steps run there (deterministic, path-checked).
    if handoff := crossrepo.retarget(state.model_copy(update={"rca": rca}), deps, bot_branch(issue, deps)):
        update |= handoff
    return update


def rca_prompt(issue: Issue, bundle: str, findings: str) -> str:
    """The RCA agent's task. Everything that came from users, logs, code or other agents is fenced as data."""
    return (
        f"Issue {issue.id} from {source_label(issue).split()[0]}, seen in repo "
        f"{issue.repo} (component '{issue.component}', {issue.language}).\n"
        + untrusted.fence("issue title", issue.title)
        + f"\nEvents: {issue.events}; versions {issue.first_version}→{issue.last_version}.\n"
        + (
            untrusted.fence("user report", json.dumps(issue.report, default=str)[:1500]) + "\n"
            if issue.report
            else ""
        )
        + "\nEvidence bundle (pre-collected, pruned):\n"
        + untrusted.fence("collected evidence", bundle)
        + "\n\n"
        + (
            "Findings from specialised subagents (verify before relying on them; cite their evidence ids):\n"
            + untrusted.fence("subagent findings", findings)
            + "\n\n"
            if findings
            else ""
        )
        + (
            f"Repository you can search: {issue.repo} — {issue.about}. "
            "Code paths are repo-relative; set location.repo to it. Investigate and submit the RCA."
            if issue.about
            else "Repositories you can search: miniride-client (the React client, at the repo root) and "
            "miniride-services (gateway/, dispatch/, payments/). Where a bug is seen is not always where it lives: "
            "when the client handles a response correctly, follow the request into the service that produced it. "
            "Code paths are repo-relative; set location.repo to the repository that holds the defect. "
            "Investigate and submit the RCA."
        )
    )
