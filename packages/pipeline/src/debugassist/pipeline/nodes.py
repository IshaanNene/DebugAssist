"""Pipeline nodes N0–N9 (minimal-but-real versions for the walking skeleton).

Deterministic nodes call backends directly (the same functions the MCP servers expose, so evidence
ids match what agents see); LLM nodes go through the LLMRunner seam; decisions go through Clef;
every write goes through the policy gate.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml
from langchain_core.tools import BaseTool, tool

from debugassist.core import untrusted
from debugassist.core.ablation import ablated
from debugassist.core.evidence import EvidenceItem
from debugassist.core.policy import ROOT, Verdict
from debugassist.core.settings import Integration, Mode
from debugassist.decisions.engine import RunContext
from debugassist.decisions.state import CompactState
from debugassist.integrations.chat import ChatMessage
from debugassist.integrations.sandbox import CommandResult, Sandbox
from debugassist.llm.runner import is_daily_quota
from debugassist.llm.spec import LLMNodeSpec, LLMResult
from debugassist.llm.workspace_tools import build_workspace_tools, changed_files, is_test_path
from debugassist.pipeline import budget, collector, crossrepo, e2e, fixplan, postmerge, pr_body, skills
from debugassist.pipeline import rca as rca_mod
from debugassist.pipeline.deps import APPS, Deps
from debugassist.pipeline.state import (
    RCA,
    FixAttempt,
    FixOutput,
    Issue,
    Mitigation,
    PRInfo,
    RCAOutput,
    ReproOutput,
    RunState,
    Ship,
    ShipOutcome,
    TestRun,
    Tier,
    Triage,
    Validation,
)

PROMPTS = Path(__file__).parent / "prompts"
PRIORITIES = ["P4", "P3", "P2", "P1", "P0"]
NON_ACTIONABLE = {"route_rca", "close_rca"}


def _prompt(name: str) -> str:
    return (PROMPTS / name).read_text()


def _llm_summary(r: LLMResult) -> dict[str, Any]:
    return {
        "status": r.status,
        "mode": r.mode,
        "model": r.model,
        "turns": r.turns,
        "cost_usd": r.cost_usd,
        "input_tokens": r.input_tokens,
        "output_tokens": r.output_tokens,
        "error": r.error,
        "tool_calls": [c.model_dump() for c in r.tool_calls],
    }


def _sandbox(state: RunState) -> Sandbox:
    assert state.issue
    return Sandbox(
        state.run_id, ROOT / "targets" / state.issue.repo, state.issue.gh_repo, state.issue.language
    )


def _code_repos_env(state: RunState) -> dict[str, str]:
    assert state.issue
    sb = _sandbox(state)
    # Service URLs for the MCP servers: localhost by default; service names inside a runtime container.
    passthrough = (
        "LOKI_URL",
        "JAEGER_URL",
        "PROMETHEUS_URL",
        "BUGDROP_URL",
        "INCIDENTS_URL",
        "DEBUGASSIST_ROOT",
    )
    env = {
        "VITALS_URL": os.environ.get("VITALS_URL", "http://localhost:8100"),
        "UNLEASH_URL": os.environ.get("UNLEASH_URL", "http://localhost:4242"),
        **{k: os.environ[k] for k in passthrough if k in os.environ},
        "CODE_REPOS": json.dumps(crossrepo.code_repos(state.run_id, state.issue, sb.worktree)),
        "DEBUGASSIST_RUN_ID": state.run_id,
        "DEBUGASSIST_MODE": state.mode,
        "PATH": os.environ.get("PATH", ""),
    }
    return env


def _top_in_app(frames: list[dict[str, Any]]) -> dict[str, Any] | None:
    in_app = [f for f in frames if f.get("in_app", True) and "vendor/" not in str(f.get("file"))]
    return in_app[-1] if in_app else (frames[-1] if frames else None)


def _pipeline_yaml(worktree: Path) -> dict[str, Any]:
    return yaml.safe_load((worktree / ".DebugAssist" / "pipeline.yaml").read_text())


def _static_problem(sb: Sandbox, comp: dict[str, Any], workdir: str) -> str | None:
    """The repository's own CI checks (lint + typecheck) must pass too: a fix CI rejects is not a fix."""
    if not comp.get("lint"):
        return None
    res = sb.run(str(comp["lint"]), workdir=workdir)
    return None if res.exit_code == 0 else f"`{comp['lint']}` (run by CI) fails:\n{res.output[-1200:]}"


def _stop_if_out_of_quota(r: LLMResult, state: RunState, node: str) -> None:
    """An exhausted daily LLM quota is an infrastructure failure, not a failed fix attempt: stop the run
    (no retries, no ship, no writes) so it can be resumed after the reset."""
    if r.status == "error" and is_daily_quota(r.error):
        raise RuntimeError(
            f"LLM provider's daily quota is exhausted ({(r.error or '')[:160]}). Resume after the reset: "
            f"debugassist run {state.issue_ref} --resume {state.run_id} --from-node {node}"
        )


TIMEOUT_MARKERS = ("Test timed out", "Exceeded timeout of", "Timeout of", "Failed: Timeout >")


def _error_signature(issue: Issue) -> str | None:
    """The production error message a reproduction must show (crashes only), e.g.
    "Cannot read properties of undefined (reading 'riderId')" from "TypeError: Cannot read …"."""
    if issue.kind != "crash":
        return None
    msg = re.sub(r"^[A-Za-z_.]*(Error|Exception)\b:?\s*", "", issue.title).strip()
    return msg or None


def _repro_problem(cmd: str, exit_code: int, output: str, issue: Issue) -> str | None:
    """Why a test run on the buggy release does not count as a reproduction (None = it does).

    A test that only times out fails with or without a fix (e.g. fake timers never advanced), and one
    that fails with some other error does not show the reported bug; both used to be accepted and then
    frozen, leaving the fix step an impossible target.
    """
    if exit_code == 0:
        return f"`{cmd}` passes on the current (buggy) code, so it does not reproduce the bug."
    if "No test files found" in output or "SyntaxError" in output or "Cannot find module" in output:
        return f"`{cmd}` failed for an unrelated reason:\n{output[-800:]}"
    if any(m in output for m in TIMEOUT_MARKERS):
        return (
            f"`{cmd}` fails only by timing out, which happens with or without a fix (fake timers never "
            f"advanced? an awaited promise that never settles?). Make it fail with the production error.\n{output[-600:]}"
        )
    sig = _error_signature(issue)
    if sig and sig not in output:
        return f"`{cmd}` fails, but not with the reported error `{sig}`; reproduce that failure.\n{output[-600:]}"
    return None


def _run_on_release(sb: Sandbox, base: str, run: Callable[[], CommandResult]) -> CommandResult | None:
    """Run with the source change reverted (tests kept), then re-apply it. None if no source change."""
    src = [f for f in changed_files(sb.diff(base)) if not is_test_path(f)]
    if not src:
        return None
    # Against the release, not HEAD: once a fix is committed (diff fixer), HEAD already contains it.
    src_diff = subprocess.run(
        ["git", "diff", base, "--", *src], cwd=sb.worktree, capture_output=True, text=True, check=True
    ).stdout
    subprocess.run(["git", "apply", "-R", "-"], input=src_diff, text=True, cwd=sb.worktree, check=True)
    try:
        return run()
    finally:
        subprocess.run(["git", "apply", "-"], input=src_diff, text=True, cwd=sb.worktree, check=True)


def _component_cfg(state: RunState, worktree: Path) -> dict[str, Any]:
    assert state.issue
    cfg = _pipeline_yaml(worktree)["components"]
    if state.issue.component == ".":
        return next(iter(cfg.values()))
    return cfg[state.issue.component]


# ---- N0 ingest ------------------------------------------------------------------------------


async def ingest(state: RunState, deps: Deps) -> dict[str, Any]:
    ref = state.issue_ref
    if ref.upper().startswith("BD-"):
        return _with_agent_type(await collector.ingest_bugdrop(ref, deps), deps)
    if not ref.upper().startswith("VIT-"):
        raise ValueError(
            f"unknown issue reference {ref!r}: expected a Vitals issue (VIT-…) or a BugDrop report (BD-…)"
        )
    async with httpx.AsyncClient(base_url=deps.vitals_url, timeout=15) as http:
        d = (await http.get(f"/api/issues/{ref.upper()}")).raise_for_status().json()
    g = d["group"]
    ev: dict[str, Any] = d.get("latest_event") or {}
    repo, gh_repo, component, language = APPS[d["app"]]
    issue = Issue(
        source="vitals",
        id=d["id"],
        url=f"{deps.vitals_ui}/issues/{d['id']}",
        title=d["title"],
        kind=d["kind"],
        app=d["app"],
        platform=g["platform"],
        version=ev.get("version", g["last_version"]),
        first_version=g["first_version"],
        last_version=g["last_version"],
        fingerprint=d["fingerprint"],
        events=g["count"],
        culprit=g.get("culprit"),
        repo=repo,
        gh_repo=gh_repo,
        component=component,
        language=language,
        latest_event=ev,
        session_id=ev.get("session_id"),
        opened_at=d.get("opened_at"),
    )
    return _with_agent_type(issue, deps)


def _with_agent_type(issue: Issue, deps: Deps) -> dict[str, Any]:
    """Resolve the agent type for this issue (harness): --agent-type, else the most specific matching type,
    else the target repo's default_agent_type (its .DebugAssist/pipeline.yaml)."""
    from debugassist.harness import agent_types

    pipeline = ROOT / "targets" / issue.repo / ".DebugAssist" / "pipeline.yaml"
    repo_default = (
        yaml.safe_load(pipeline.read_text()).get("default_agent_type") if pipeline.is_file() else None
    )
    t, why = agent_types.resolve(
        source=issue.source,
        kind=issue.kind,
        repo=issue.repo,
        language=issue.language,
        repo_default=repo_default,
        override=deps.extra.get("agent_type"),
    )
    deps.agent_type = t.model_dump()
    return {"issue": issue, "agent_type": t.name, "agent_type_reason": why}


# ---- N1 auto_triage -------------------------------------------------------------------------


def _source_label(issue: Issue) -> str:
    return "BugDrop report" if issue.source == "bugdrop" else "Vitals issue"


def _notify(deps: Deps, run_id: str, msg: ChatMessage) -> dict[str, Any]:
    """Every chat message goes through the write gate and the audit log (dry-run → not sent)."""
    verdict = deps.gate.verdict("chat.message")
    result: dict[str, Any] = {"to": msg.to, "mode": "dry_run"}
    if verdict is Verdict.LIVE:
        try:
            result = deps.chat.send(msg)
        except httpx.HTTPError as exc:  # a chat outage never fails the run
            result = {"to": msg.to, "mode": deps.chat.mode, "error": f"{type(exc).__name__}: {exc}"[:200]}
    deps.gate.record(
        "chat.message", verdict, run_id=run_id, detail={"to": msg.to, "title": msg.title}, result=result
    )
    return {"kind": "chat", "title": msg.title, **result}


def _link_source(
    deps: Deps, state: RunState, links: list[tuple[str, str | None, str | None]], outcome: str
) -> list[dict[str, Any]]:
    """Attach links to the Vitals issue / BugDrop report and move the report's status along."""
    issue = state.issue
    assert issue
    if issue.source == "bugdrop":
        base = f"{deps.bugdrop_url}/api/reports/{issue.id}"
    elif issue.source == "vitals":
        base = f"{deps.vitals_url}/api/issues/{issue.id}"
    else:
        return []
    notes: list[dict[str, Any]] = []
    verdict = deps.gate.verdict("source.link")
    for kind, url, title in links:
        if not url:
            continue
        result: Any = "dry_run"
        if verdict is Verdict.LIVE:
            try:
                httpx.post(
                    f"{base}/links", json={"kind": kind, "url": url, "title": title or ""}, timeout=10
                ).raise_for_status()
                result = "linked"
            except httpx.HTTPError as exc:
                result = f"failed: {type(exc).__name__}"
        deps.gate.record(
            "source.link", verdict, run_id=state.run_id, detail={"issue": issue.id, "url": url}, result=result
        )
        notes.append({"kind": "link", "issue": issue.id, "url": url, "result": result})
    if issue.source == "bugdrop" and verdict is Verdict.LIVE:
        status = "in_progress" if outcome in ("open_pr", "draft_pr") else "triaged"
        with contextlib.suppress(httpx.HTTPError):  # a convenience; the links above are what matter
            httpx.post(f"{base}/status", json={"status": status}, timeout=10).raise_for_status()
    return notes


def _jira_label(issue_id: str) -> str:
    """One Jira ticket per source issue: vitals-vit-1001, bugdrop-bd-1001."""
    return f"{'bugdrop' if issue_id.upper().startswith('BD-') else 'vitals'}-{issue_id.lower()}"


def _oncall(catalog: dict[str, Any], team: str) -> str:
    people = catalog["teams"].get(team, {}).get("oncall") or ["unassigned"]
    return str(people[datetime.now(UTC).isocalendar().week % len(people)])


async def auto_triage(state: RunState, deps: Deps) -> dict[str, Any]:
    from debugassist.mcp_servers import code_search

    issue = state.issue
    assert issue
    frames: list[dict[str, Any]] = issue.latest_event.get("frames") or []
    top = _top_in_app(frames)
    owner_team, owner_source = None, "clef"
    if top and top.get("file"):
        owners = code_search.codeowners_for(issue.repo, str(top["file"]))
        owner_team = owners.get("team")
        owner_source = "codeowners" if owner_team else "clef"
    flags: list[dict[str, Any]] = []
    versions: dict[str, Any] = {}
    if issue.fingerprint:
        async with httpx.AsyncClient(base_url=deps.vitals_url, timeout=15) as http:
            flags = (await http.get(f"/api/groups/{issue.fingerprint}/flags")).json()
            versions = (
                await http.get(f"/api/groups/{issue.fingerprint}/distribution", params={"by": "version"})
            ).json()
    teams = {k: v["description"] for k, v in deps.catalog["teams"].items()}
    cs = (
        CompactState()
        .add(
            "issue",
            {
                "title": issue.title,
                "kind": issue.kind,
                "app": issue.app,
                "events": issue.events,
                "versions": f"{issue.first_version}→{issue.last_version}",
                "culprit": issue.culprit,
            },
            priority=0,
        )
        .add(
            "stack",
            [f"{f['function']} ({f['file']}:{f.get('line')})" for f in reversed(frames[-6:])],
            priority=1,
        )
        .add(
            "affected_sessions_by_version",
            [
                {k: r[k] for k in ("value", "sessions", "affected_sessions")}
                for r in versions.get("values", [])
            ],
            priority=2,
        )
        .add("flag_exposure", flags, priority=3)
    )
    if issue.report:
        cs.add(
            "user_report",
            {k: issue.report.get(k) for k in ("description", "route", "flags", "network", "device", "city")},
            priority=0,
        )
    d = await deps.engine.decide(
        "D01", cs, params={"teams": teams}, ctx=RunContext(run_id=state.run_id, issue_id=issue.id)
    )
    level = round(float(d.chosen["priority"]))
    priority = PRIORITIES[max(0, min(4, level))]
    severity_levels = [
        "cosmetic",
        "minor annoyance",
        "degraded feature",
        "feature unusable",
        "crash or data loss",
    ]
    severity = severity_levels[max(0, min(4, round(float(d.chosen["severity"]))))]
    team = owner_team or str(d.chosen["owning_team"])
    triage = Triage(
        priority=priority,
        severity=severity,
        owner_team=team,
        oncall=_oncall(deps.catalog, team),
        owner_source=owner_source,
        customer_impacting=float(d.probabilities["customer_impacting"]["true"]),
        worth_agent_run=float(d.probabilities["worth_agent_run"]["true"]),
    )
    decisions = [*state.decisions, d.ledger_id or ""]
    # D2: same root cause as an open issue or a recent report? Then attach to it instead of a second run.
    candidates = await collector.dedup_candidates(issue, deps)
    if candidates:
        d2 = await deps.engine.decide(
            "D02",
            CompactState()
            .add("new_issue", collector.issue_summary(issue), priority=0)
            .add("open_candidates", candidates, priority=1),
            params={"candidates": [*candidates, {"id": "none", "description": "none of these: a new issue"}]},
            ctx=RunContext(run_id=state.run_id, issue_id=issue.id),
        )
        decisions.append(d2.ledger_id or "")
        triage.dedup = {
            "chosen": d2.chosen.get("duplicate_of"),
            "p": d2.p,
            "band": d2.band,
            "action": d2.action,
        }
        if d2.action == "mark_duplicate":
            triage.duplicate_of = str(d2.chosen["duplicate_of"])
            note = (
                f"{issue.source} {issue.id} looks like a duplicate of {triage.duplicate_of} "
                f"(Clef D02 p={d2.p:.2f}); attached here, no new investigation started."
            )
            dup_label = _jira_label(triage.duplicate_of)
            verdict = deps.gate.verdict("jira.comment")
            target = deps.jira.find_open(dup_label) if verdict is Verdict.LIVE else None
            if target:
                deps.jira.comment(target.key, [("para", note), ("para", issue.url)])
                triage.jira_key, triage.jira_url, triage.jira_mode = target.key, target.url, target.mode
            deps.gate.record(
                "jira.comment",
                verdict,
                run_id=state.run_id,
                detail={"duplicate_of": triage.duplicate_of},
                result=triage.jira_key,
            )
            return {"triage": triage, "decisions": decisions, "status": "duplicate"}
    # Jira ticket (policy-gated)
    blocks = [
        (
            "para",
            f"Opened automatically from {'Vitals issue' if issue.source == 'vitals' else 'BugDrop report'} {issue.id} "
            f"({issue.events} events, {issue.app} {issue.first_version}→{issue.last_version}).",
        ),
        ("heading", "Signal"),
        (
            "code",
            f"{issue.title}\n"
            + "\n".join(f"  at {f['function']} ({f['file']}:{f.get('line')})" for f in reversed(frames[-6:])),
        ),
        ("heading", "Triage"),
        (
            "bullet",
            f"Priority {priority} (Clef), severity: {severity}\nOwner: {team} (from {owner_source}); on-call {triage.oncall}\n"
            f"Customer impacting: p={triage.customer_impacting:.2f}; worth an agent run: p={triage.worth_agent_run:.2f}",
        ),
        ("para", f"{'Vitals' if issue.source == 'vitals' else 'BugDrop'}: {issue.url}"),
        ("para", f"DebugAssist run {state.run_id} is investigating."),
    ]
    verdict = deps.gate.verdict("jira.create_issue")
    label = _jira_label(issue.id)
    if verdict is Verdict.LIVE:
        ticket = deps.jira.find_open(label)  # one ticket per Vitals issue: reuse it on re-runs
        if ticket:
            deps.jira.comment(ticket.key, [("para", f"DebugAssist run {state.run_id} picked this up again.")])
        else:
            ticket = deps.jira.create(
                f"[{priority}] {issue.title[:180]}",
                blocks,
                priority,
                ["bug", "debugassist", issue.app, label],
            )
        deps.jira.transition(ticket.key, "In Progress")
        triage.jira_key, triage.jira_url, triage.jira_mode = ticket.key, ticket.url, ticket.mode
    deps.gate.record(
        "jira.create_issue", verdict, run_id=state.run_id, detail={"issue": issue.id}, result=triage.jira_key
    )
    notes = list(state.notifications)
    if priority in ("P0", "P1"):
        msg = ChatMessage(
            to=f"@{triage.oncall}",
            title=f"{priority} · {issue.title[:200]}",
            text=f"Paging {team} on-call. DebugAssist has started root-cause analysis.",
            level="alert",
            links={_source_label(issue): issue.url, "Jira": triage.jira_url or ""},
            fields={"App": f"{issue.app} {issue.last_version}", "Ticket": triage.jira_key or "-"},
        )
        notes.append(_notify(deps, state.run_id, msg))
    return {"triage": triage, "decisions": decisions, "notifications": notes}


# ---- N2 context_collector -------------------------------------------------------------------


async def context_collector(state: RunState, deps: Deps) -> dict[str, Any]:
    issue = state.issue
    assert issue
    # The sandbox worktree at the shipped release: code search and the fix both work on it.
    sb = _sandbox(state)
    sb.create(f"v{issue.last_version}", _bot_branch(issue, deps))
    os.environ["CODE_REPOS"] = json.dumps(crossrepo.code_repos(state.run_id, issue, sb.worktree))
    return await collector.collect(state, deps)


def _bot_branch(issue: Issue, deps: Deps) -> str:
    branch = (
        f"debugassist/{issue.id.lower()}-{re.sub(r'[^a-z0-9]+', '-', issue.title.lower())[:40].strip('-')}"
    )
    if deps.settings.mode(Integration.GITHUB) is not Mode.LIVE:
        branch += "-mock"  # never collide with (and clean up) a live run's worktree for the real PR branch
    return branch


def _bundle(items: list[EvidenceItem], budget_chars: int = 40_000) -> str:
    parts: list[str] = []
    used = 0
    for it in items:
        body = json.dumps(it.data, default=str)
        chunk = f"### {it.id} — {it.summary}\n{body[:9000]}\n"
        if used + len(chunk) > budget_chars:
            parts.append(
                f"### {it.id} — {it.summary}\n(omitted for length; call the matching tool for details)\n"
            )
            continue
        parts.append(chunk)
        used += len(chunk)
    return "\n".join(parts)


# ---- N3 classify_rca ------------------------------------------------------------------------


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
    env = _code_repos_env(state)
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
    spec = LLMNodeSpec(node="classify_rca", system_prompt=_prompt("rca_system.md") + skill_prompt, **cfg)
    prompt = rca_prompt(issue, _bundle(st.evidence), rca_mod.findings_text(findings))
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
    _stop_if_out_of_quota(r, state, "classify_rca")
    rca.llm = _llm_summary(r)
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
    if handoff := crossrepo.retarget(state.model_copy(update={"rca": rca}), deps, _bot_branch(issue, deps)):
        update |= handoff
    return update


def rca_prompt(issue: Issue, bundle: str, findings: str) -> str:
    """The RCA agent's task. Everything that came from users, logs, code or other agents is fenced as data."""
    return (
        f"Issue {issue.id} from {'Vitals' if issue.source == 'vitals' else 'BugDrop'}, seen in repo "
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
        + "Repositories you can search: miniride-client (the React client, at the repo root) and "
        "miniride-services (gateway/, dispatch/, payments/). Where a bug is seen is not always where it lives: "
        "when the client handles a response correctly, follow the request into the service that produced it. "
        "Code paths are repo-relative; set location.repo to the repository that holds the defect. "
        "Investigate and submit the RCA."
    )


# ---- N4 mitigate ----------------------------------------------------------------------------


def _flag_names() -> list[str]:
    from debugassist.mcp_servers import feature_flags as ff

    try:
        return [str(f["name"]) for f in ff.list_flags()["flags"]]
    except Exception:  # flag service unreachable (mock runs): fall back to the leading identifier
        return []


def known_flag(raw: str, known: list[str]) -> str | None:
    """The flag `raw` names: an exact match, else the first known flag named in it as a whole word. Without a
    flag list, the leading identifier of `raw` ("notif_router_v2 (…)" → notif_router_v2)."""
    if raw in known:
        return raw
    if not known:
        m = re.match(r"\s*([A-Za-z0-9_.-]+)", raw)
        return m.group(1) if m and m.group(1).lower() not in ("none", "n/a") else None
    hits = [
        (m.start(), name) for name in known if (m := re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", raw))
    ]
    return min(hits)[1] if hits else None


async def mitigate(state: RunState, deps: Deps) -> dict[str, Any]:
    from debugassist.mcp_servers import feature_flags as ff

    issue, rca = state.issue, state.rca
    assert issue and rca and rca.output
    corr_items = [e.data for e in state.evidence if e.kind == "flag_correlation"]
    raw = rca.output.implicated_flag or (corr_items[0]["flag"] if corr_items else None)
    # The RCA's flag is free text from the LLM ("notif_router_v2 (flag is off …)"): only a real flag acts.
    flag = known_flag(raw, _flag_names()) if raw else None
    if not flag or not issue.fingerprint:
        return {"mitigation": Mitigation(detail="no feature flag implicated; nothing to roll back")}
    corr = ff.flag_crash_correlation(issue.fingerprint, flag)
    current = ff.get_flag(flag)
    cs = (
        CompactState()
        .add("flag", {"name": flag, "rollout_pct": current["rollout_pct"]}, priority=0)
        .add(
            "crash_rates",
            {
                "exposed": corr["exposed"],
                "unexposed": corr["unexposed"],
                "z": corr["z"],
                "p_value": corr["p_value"],
                "share_of_affected_exposed": corr["share_of_affected_exposed"],
            },
            priority=0,
        )
        .add("rca", {"summary": rca.output.summary, "root_cause": rca.output.root_cause}, priority=1)
    )
    d11 = await deps.engine.decide("D11", cs, ctx=RunContext(run_id=state.run_id, issue_id=issue.id))
    m = Mitigation(
        flag=flag,
        correlation={
            k: corr[k]
            for k in ("exposed", "unexposed", "z", "p_value", "significant", "share_of_affected_exposed")
        },
        decision={"p": d11.p, "band": d11.band, "action": d11.action},
    )
    if d11.action == "rollback_flag" and corr["significant"] and not current["rollout_pct"]:
        m.detail = f"{flag}: rollback warranted, but the flag is already at 0% — nothing to roll back"
    elif d11.action == "rollback_flag" and corr["significant"]:
        verdict = deps.gate.verdict("flags.rollback")
        if verdict is Verdict.APPROVAL:
            from langgraph.types import interrupt

            approved = interrupt(
                {
                    "question": f"Roll back {flag} from {current['rollout_pct']}% to 0%?",
                    "flag": flag,
                    "correlation": m.correlation,
                }
            )
            verdict = Verdict.LIVE if approved else Verdict.DRY_RUN
        res = ff.rollback_flag(
            flag, 0, reason=f"{issue.id}: {rca.output.summary[:200]}", dry_run=verdict is not Verdict.LIVE
        )
        m.action = "rolled_back" if res["applied"] else "dry_run"
        m.rolled_back_from = int(res["from_percent"])
        m.detail = f"{flag}: {res['from_percent']}% → 0% ({'applied' if res['applied'] else 'dry run — policy requires approval'})"
    else:
        m.detail = f"{flag}: no rollback (Clef band {d11.band}, significant={corr['significant']})"
    return {"mitigation": m, "decisions": [*state.decisions, d11.ledger_id or ""]}


# ---- N5 fix ---------------------------------------------------------------------------------


def _apply_diff(sb: Sandbox) -> Any:
    def apply(diff: str) -> None:
        subprocess.run(
            ["git", "apply", "--whitespace=nowarn", "-"], input=diff, text=True, cwd=sb.worktree, check=True
        )

    return apply


def _revert_non_tests(sb: Sandbox) -> None:
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=sb.worktree,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for line in status.splitlines():
        path = line[3:].strip().strip('"')
        if is_test_path(path):
            continue
        if line.startswith("??"):
            (sb.worktree / path).unlink(missing_ok=True)
        else:
            subprocess.run(["git", "checkout", "-q", "--", path], cwd=sb.worktree, check=False)


def _new_test_files(sb: Sandbox) -> list[str]:
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=sb.worktree,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    files = [line[3:].strip().strip('"') for line in status.splitlines()]
    tests = [f for f in files if is_test_path(f) and (sb.worktree / f).is_file()]
    return sorted(tests, key=lambda f: (sb.worktree / f).stat().st_mtime)


def _test_cmd(language: str, test_file: str, component: str) -> str:
    """The pipeline, not the agent, decides how the reproduction test is run."""
    rel = test_file if component == "." else test_file.removeprefix(f"{component}/")
    if language == "python":
        return f"uv run --offline pytest -q {rel}"
    if language == "go":
        pkg = "./" + rel.rsplit("/", 1)[0] if "/" in rel else "."
        return f"go test {pkg}"
    return f"pnpm exec vitest run {rel}"


def _run_test(sb: Sandbox, issue: Issue, cmd: str) -> CommandResult:
    """Unit/integration tests run in the sandbox; E2E specs run against a build of the worktree."""
    if e2e.is_e2e_cmd(cmd):
        return e2e.run(sb, _pipeline_yaml(sb.worktree), issue.component, cmd)
    return sb.run(cmd, workdir=issue.component)


def _repro_cmd(issue: Issue, test_file: str) -> str:
    rel = test_file if issue.component == "." else test_file.removeprefix(f"{issue.component}/")
    if rel.startswith("e2e/"):
        return e2e.e2e_cmd(test_file, issue.component)
    return _test_cmd(issue.language, test_file, issue.component)


def _tier_problem(tier: Tier, issue: Issue, test_file: str) -> str | None:
    rel = test_file if issue.component == "." else test_file.removeprefix(f"{issue.component}/")
    if tier == "e2e_env" and not rel.startswith("e2e/"):
        return f"this step needs a Playwright spec under e2e/, not {test_file}."
    if tier != "e2e_env" and rel.startswith("e2e/"):
        return f"this step needs a {tier} test next to the existing tests, not a Playwright spec."
    return None


def _e2e_tool(sb: Sandbox, issue: Issue) -> BaseTool:
    """Lets the agent check its spec: the pipeline builds the worktree and runs the spec in the isolated
    E2E runner (the agent's own sandbox has no network)."""

    @tool
    def run_e2e(test_file: str) -> str:
        """Build the app from the worktree and run one Playwright spec (e2e/….spec.ts) against the live
        backends. Slow (about a minute): use it to check your spec before submitting."""
        if _tier_problem("e2e_env", issue, test_file) or not (sb.worktree / test_file).is_file():
            return f"{test_file} is not an existing spec under e2e/"
        res = e2e.run(
            sb, _pipeline_yaml(sb.worktree), issue.component, e2e.e2e_cmd(test_file, issue.component)
        )
        return f"exit code {res.exit_code}\n{res.output[-3500:]}"

    return run_e2e


def fix_contract_problem(
    sb: Sandbox, issue: Issue, comp: dict[str, Any], base: str, cmd: str, test_file: str
) -> str | None:
    """Why the worktree's change is not (yet) a proven fix; None when it is: the reproduction test still
    fails on the release with only the source change reverted, passes with it, and the suite and the
    repository's CI checks pass. A test weakened to pass is therefore rejected."""
    if not (sb.worktree / test_file).is_file():
        return f"the reproduction test {test_file} is missing; restore it"
    before = _run_on_release(sb, base, lambda: _run_test(sb, issue, cmd))
    if before is None:
        return "you have not changed any source file yet"
    if problem := _repro_problem(cmd, before.exit_code, before.output, issue):
        return (
            f"with your source change reverted, the reproduction test no longer reproduces the bug: {problem}"
        )
    res = _run_test(sb, issue, cmd)
    if res.exit_code != 0:
        return f"the reproduction test still fails with your change:\n{res.output[-1200:]}"
    suite = sb.run(str(comp["test"]), workdir=issue.component)
    if suite.exit_code != 0:
        return f"the component suite fails:\n{suite.output[-1200:]}"
    return _static_problem(sb, comp, issue.component)


def _reset_to(sb: Sandbox, base: str) -> None:
    # Every attempt (and a resumed run) starts from the release tag, not the branch head: after a PR
    # the bot branch holds the previous fix commit. Ignored dirs (node_modules…) survive.
    subprocess.run(["git", "reset", "-q", "--hard", base], cwd=sb.worktree, check=True)
    subprocess.run(["git", "clean", "-qfd"], cwd=sb.worktree, check=False)


async def fix(state: RunState, deps: Deps) -> dict[str, Any]:
    """Plan once (D12–D14), then two enforced phases per attempt: (1) reproduce — tests only, must fail on
    the release, climbing the tier ladder until a tier reproduces; (2) fix — make it pass."""
    issue, rca = state.issue, state.rca
    assert issue and rca and rca.output
    sb = _sandbox(state)
    comp = _component_cfg(state, sb.worktree)
    attempt = len(state.fix_attempts) + 1
    base = f"v{issue.last_version}"
    _reset_to(sb, base)
    if attempt == 1:
        res = sb.install(str(comp["setup"]), workdir=issue.component)
        if res.exit_code:
            raise RuntimeError(f"dependency install failed: {res.output[-1500:]}")
    costs = dict(state.costs)
    decisions = list(state.decisions)
    plan = state.fix_plan
    if plan is None:
        plan, ledgers = await fixplan.plan(sb, state, deps, _pipeline_yaml(sb.worktree))
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
                "validation output", json.dumps(state.validation.attempts[-1], default=str)[:3000]
            )
            + "\nTry a different approach.\n"
        )
    fa = FixAttempt(n=attempt)

    # Phase 1: reproduce (only test files may be written), up the ladder from the last tier that worked
    last = next((a.tier for a in reversed(state.fix_attempts) if a.tier), None)
    ladder = plan.ladder[plan.ladder.index(last) :] if last in plan.ladder else plan.ladder
    repro_cfg: dict[str, Any] = {**cfg, "max_turns": min(15, int(cfg["max_turns"]))}
    for tier in ladder:
        _reset_to(sb, base)
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
            node=node, system_prompt=_prompt("reproduce_system.md") + skill_prompt, **repro_cfg
        )
        tools = (
            build_workspace_tools(
                sb, allow_edits=True, allow_commands=True, editable=is_test_path, workdir=issue.component
            )
            + skill_tools
        )
        if tier == "e2e_env":
            tools.append(_e2e_tool(sb, issue))
        feedback = ""

        def check_repro(out: dict[str, Any], bound_tier: Tier = tier) -> str | None:
            path = str(out.get("test_file", ""))
            if not is_test_path(path) or not (sb.worktree / path).is_file():
                return f"{path} does not exist as a test file. Create it with write_file first."
            if problem := _tier_problem(bound_tier, issue, path):
                return problem
            cmd = _repro_cmd(issue, path)
            res = _run_test(sb, issue, cmd)
            if problem := _repro_problem(cmd, res.exit_code, res.output, issue):
                return problem
            if problem := _static_problem(sb, comp, issue.component):
                return f"the test reproduces the bug, but {problem}\nClean up the test file (e.g. unused imports)."
            return None

        tried: dict[str, Any] = {"tier": tier}
        for _ in range(2):
            r1 = await deps.runner(_apply_diff(sb)).run(
                repro_spec,
                context + guide + feedback + "\nWrite the reproduction test, run it if you can, then submit.",
                ReproOutput,
                tools=tools,
                diff_fn=lambda: sb.diff(base),
                validate_output=check_repro,
            )
            _stop_if_out_of_quota(r1, state, "fix")
            costs[node] = costs.get(node, 0.0) + r1.cost_usd
            fa.llm[node] = _llm_summary(r1)
            _revert_non_tests(sb)  # source is read-only while reproducing, whatever the agent ran
            out = (
                r1.output
                if r1.output and (sb.worktree / str(r1.output.get("test_file", ""))).is_file()
                else None
            )
            if out is None:
                # The model sometimes stops without submitting: trust the worktree, not its word.
                helper = e2e.HELPER_PATH if issue.component == "." else f"{issue.component}/{e2e.HELPER_PATH}"
                written = [f for f in _new_test_files(sb) if f != helper]
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
            cmd = _repro_cmd(issue, fa.repro.test_file)
            run = _run_test(sb, issue, cmd)
            fa.repro_run = {"command": cmd, "exit_code": run.exit_code, "output_tail": run.output[-2500:]}
            problem = (
                _tier_problem(tier, issue, fa.repro.test_file)
                or _repro_problem(cmd, run.exit_code, run.output, issue)
                or _static_problem(sb, comp, issue.component)
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
        tools.append(_e2e_tool(sb, issue))
    skill_prompt, skill_tools = skills.for_node(deps.agent_type, "fix", issue)
    tools += skill_tools
    fix_spec = LLMNodeSpec(
        node=f"fix_{attempt}" if attempt > 1 else "fix",
        system_prompt=_prompt("fix_system.md") + skill_prompt,
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

    r2 = await deps.runner(_apply_diff(sb)).run(
        fix_spec, prompt, FixOutput, tools=tools, diff_fn=lambda: sb.diff(base), validate_output=check_fix
    )
    _stop_if_out_of_quota(r2, state, "fix")
    costs[fix_spec.node] = costs.get(fix_spec.node, 0.0) + r2.cost_usd
    fa.llm["fix"] = _llm_summary(r2)
    fa.output = FixOutput.model_validate(r2.output) if r2.output else None
    fa.diff = sb.diff(base)
    fa.files = changed_files(fa.diff)
    return {
        "fix_attempts": [*state.fix_attempts, fa],
        "costs": costs,
        "fix_plan": plan,
        "decisions": decisions,
    }


# ---- N6 validate ----------------------------------------------------------------------------


async def validate(state: RunState, deps: Deps) -> dict[str, Any]:
    """Failing-before / passing-after proof on the reproduction test, plus the full component suite."""
    issue = state.issue
    assert issue and state.fix_attempts
    sb = _sandbox(state)
    comp = _component_cfg(state, sb.worktree)
    fa = state.fix_attempts[-1]
    v = state.validation or Validation()
    record: dict[str, Any] = {"attempt": fa.n, "tier": fa.tier, "tiers_tried": fa.tiers_tried}
    src = [f for f in fa.files if not is_test_path(f)]
    if not fa.repro_verified or not fa.repro:
        record.update(result="no reproduction test that fails on the release", repro_run=fa.repro_run)
    elif not src:
        record.update(result="no source change")
    else:
        cmd = str(fa.repro_run["command"])
        after = _run_test(sb, issue, cmd)
        v.passing_after = TestRun(
            label=f"reproduction test ({fa.tier}) with the fix",
            command=cmd,
            exit_code=after.exit_code,
            output_tail=after.output[-3000:],
        )
        # Failing-before: reverse-apply only the source change, keep the test, run, re-apply.
        src_diff = subprocess.run(
            ["git", "diff", "--", *src], cwd=sb.worktree, capture_output=True, text=True, check=True
        ).stdout
        subprocess.run(["git", "apply", "-R", "-"], input=src_diff, text=True, cwd=sb.worktree, check=True)
        try:
            before = _run_test(sb, issue, cmd)
        finally:
            subprocess.run(["git", "apply", "-"], input=src_diff, text=True, cwd=sb.worktree, check=True)
        v.failing_before = TestRun(
            label=f"reproduction test ({fa.tier}) on the release (expected to fail)",
            command=cmd,
            exit_code=before.exit_code,
            output_tail=before.output[-3000:],
        )
        if before_problem := _repro_problem(cmd, before.exit_code, before.output, issue):
            record.update(failing_before_problem=before_problem[:600])
        suite = sb.run(str(comp["test"]), workdir=issue.component)
        v.suite = TestRun(
            label="full component suite with the fix",
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
    v.attempts.append(record)
    return {"validation": v}


async def decide_retry(state: RunState, deps: Deps) -> bool:
    """D15 inside the fixed attempt cap."""
    v = state.validation
    validation: dict[str, Any] = deps.agent_type.get("validation") or {}
    cap = int(validation.get("max_attempts", 3))
    if v is None or v.passed or len(state.fix_attempts) >= cap:
        return False
    if (
        "result" in v.attempts[-1]
    ):  # no reproduction or no change: always worth another attempt within the cap
        return True
    cs = (
        CompactState()
        .add("last_attempt", v.attempts[-1], priority=0)
        .add("attempts_so_far", len(state.fix_attempts), priority=1)
    )
    d15 = await deps.engine.decide("D15", cs, ctx=RunContext(run_id=state.run_id, issue_id=state.issue_ref))
    return d15.action == "retry"


# ---- N7 ship_gate ---------------------------------------------------------------------------


async def ship_gate(state: RunState, deps: Deps) -> dict[str, Any]:
    rca, v = state.rca, state.validation
    if state.fix_plan and state.fix_plan.skip:
        outcome: ShipOutcome = "escalate" if state.fix_plan.skip.startswith("needs a human") else "rca_only"
        return {"ship": Ship(outcome=outcome, decision={"reason": state.fix_plan.skip})}
    if rca is None or not rca.actionable or not state.fix_attempts:
        return {"ship": Ship(outcome="rca_only", decision={"reason": "not actionable or no fix"})}
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
    has_fix = fa.repro_verified and any(not is_test_path(f) for f in fa.files)
    if not has_fix:
        outcome = "rca_only"  # no verified reproduction or no source change: nothing to put in a PR
    elif not (v and v.passed) and outcome == "open_pr":
        outcome = "draft_pr"  # never a ready PR without validation proof
    return {
        "ship": Ship(
            outcome=outcome,
            risk=float(d16.chosen.get("risk", 0)),
            decision={"p": d16.p, "band": d16.band, "chosen": d16.chosen},
        ),  # pyright: ignore[reportArgumentType]
        "decisions": [*state.decisions, d16.ledger_id or ""],
    }


# ---- N8 pr_and_notify -----------------------------------------------------------------------


async def pr_and_notify(state: RunState, deps: Deps) -> dict[str, Any]:
    issue, tr, rca, ship = state.issue, state.triage, state.rca, state.ship
    assert issue and rca and ship
    notes = list(state.notifications)
    out: dict[str, Any] = {}
    jira_blocks: list[tuple[str, str]] = []
    if rca.output:
        jira_blocks = [
            ("heading", "Root cause (DebugAssist)"),
            ("para", rca.output.summary),
            ("para", rca.output.root_cause),
            ("bullet", "\n".join(f"{c.text} [{', '.join(c.evidence_ids)}]" for c in rca.output.claims[:8])),
        ]
    if ship.outcome in ("open_pr", "draft_pr") and state.fix_attempts:
        sb = _sandbox(state)
        fa = state.fix_attempts[-1]
        loc = rca.output.location if rca.output else None
        scope = (loc.file.split("/")[-2] if loc and "/" in loc.file else issue.component.strip("./")) or "app"
        title = (
            fa.output.commit_title
            if fa.output and fa.output.commit_title.startswith(("fix", "perf", "refactor"))
            else f"fix({scope}): {issue.title[:70]}"
        )[:100]
        sb.commit(
            f"{title}\n\n{rca.output.root_cause if rca.output else ''}\n\nVitals: {issue.id}"
            + (f"\nJira: {tr.jira_key}" if tr and tr.jira_key else "")
        )
        branch = subprocess.run(
            ["git", "branch", "--show-current"], cwd=sb.worktree, capture_output=True, text=True, check=True
        ).stdout.strip()
        base = f"release/{issue.last_version}"
        push_v = deps.gate.verdict("github.push_branch", repo=issue.gh_repo, branch=branch)
        pr_v = deps.gate.verdict("github.open_pr", repo=issue.gh_repo)
        if push_v is Verdict.LIVE and pr_v is Verdict.LIVE:
            if not deps.github.remote_branch_exists(issue.gh_repo, base):
                raise RuntimeError(
                    f"base branch {base} is not on GitHub; push it first (debugassist scenario inject --push)"
                )
            deps.github.push(sb.worktree, branch)
            pr = deps.github.open_pr(
                issue.gh_repo, branch, base, title, pr_body.pr_body(state), draft=ship.outcome == "draft_pr"
            )
            out["pr"] = PRInfo(
                url=pr.url, number=pr.number, branch=branch, base=base, draft=pr.draft, mode=pr.mode
            )
        deps.gate.record(
            "github.open_pr",
            pr_v,
            run_id=state.run_id,
            detail={"repo": issue.gh_repo, "branch": branch, "base": base},
            result=out["pr"].model_dump() if out.get("pr") else None,
        )
    pr_info: PRInfo | None = out.get("pr")
    if tr and tr.jira_key:
        if pr_info:
            jira_blocks.append(("para", f"Pull request: {pr_info.url}"))
            deps.jira.link(tr.jira_key, pr_info.url, f"PR #{pr_info.number} (DebugAssist)")
        deps.jira.comment(tr.jira_key, jira_blocks or [("para", f"DebugAssist outcome: {ship.outcome}")])
        deps.jira.transition(tr.jira_key, "In Review" if pr_info else "In Progress")
        deps.gate.record("jira.comment", Verdict.LIVE, run_id=state.run_id, detail={"key": tr.jira_key})
    # Link the PR / ticket back to the user-facing issue (Vitals or BugDrop).
    links: list[tuple[str, str | None, str | None]] = (
        [("jira", tr.jira_url, tr.jira_key)] if tr and tr.jira_url and tr.jira_url.startswith("http") else []
    )
    if pr_info:
        links.append(("pr", pr_info.url, f"PR #{pr_info.number} (DebugAssist)"))
    notes += _link_source(deps, state, links, ship.outcome)
    if tr:
        o = rca.output
        msg = ChatMessage(
            to=f"@{tr.oncall}",
            title=(
                f"Fix ready for review: {issue.title[:180]}"
                if pr_info
                else f"{ship.outcome.replace('_', ' ')}: {issue.title[:180]}"
            ),
            text=(o.summary if o else "No root cause produced.")[:1500],
            level="success" if pr_info and not pr_info.draft else "warning" if pr_info else "info",
            links={
                "PR": pr_info.url if pr_info else "",
                "Jira": tr.jira_url or "",
                _source_label(issue): issue.url,
            },
            fields={
                "Outcome": ship.outcome,
                "Location": f"{o.location.file} → {o.location.function}" if o else "-",
                "Proof": (
                    f"{state.fix_attempts[-1].tier or '-'} test fails before, passes after"
                    if state.validation and state.validation.passed and state.fix_attempts
                    else "not validated"
                ),
            },
        )
        notes.append(_notify(deps, state.run_id, msg))
    return {**out, "notifications": notes}


async def post_merge_watch(state: RunState, deps: Deps) -> dict[str, Any]:
    """Start watching the issue after a PR; `debugassist watch <run>` checks it after merge + deploy (D17)."""
    w = postmerge.start(state)
    if w is None:
        return {"status": "done"}
    return {
        "status": "watching",
        "watch": w,
        "notifications": [
            *state.notifications,
            {"kind": "watch", "detail": f"watching after merge + deploy: debugassist watch {state.run_id}"},
        ],
    }


# Public names for the post-PR tools (diff fixer, open-in-your-machine), which reuse the fix machinery.
sandbox_for = _sandbox
component_cfg = _component_cfg
pipeline_yaml = _pipeline_yaml
run_test = _run_test
e2e_tool = _e2e_tool
llm_summary = _llm_summary
stop_if_out_of_quota = _stop_if_out_of_quota
