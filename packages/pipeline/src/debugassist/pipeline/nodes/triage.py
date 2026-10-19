"""N1 auto_triage: priority, severity, owner and on-call; the Jira ticket and the first chat message."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import httpx

from debugassist.core.policy import ROOT, Verdict
from debugassist.decisions.engine import RunContext
from debugassist.decisions.state import CompactState
from debugassist.integrations.chat import ChatMessage
from debugassist.pipeline import (
    collector,
)
from debugassist.pipeline.deps import Deps
from debugassist.pipeline.nodes.common import PRIORITIES, pipeline_yaml, source_label, top_in_app
from debugassist.pipeline.notify import notify
from debugassist.pipeline.state import (
    Issue,
    RunState,
    Triage,
)


def jira_label(issue_id: str) -> str:
    """One Jira ticket per source issue: vitals-vit-1001, bugdrop-bd-1001."""
    return f"{'bugdrop' if issue_id.upper().startswith('BD-') else 'vitals'}-{issue_id.lower()}"


def repo_owner(issue: Issue) -> tuple[str, str]:
    """(owner, where it came from) for a repository outside the MiniRide catalog."""
    from debugassist.mcp_servers import code_search

    try:
        rule = code_search.codeowners_for(issue.repo, "README.md")  # the rule covering the repository root
        owners = cast(list[str], rule.get("owners") or [])
        owner = rule.get("team") or (owners[0] if owners else None)
    except (OSError, ValueError):
        owner = None
    if owner:
        return str(owner), "codeowners"
    try:
        comps: Any = pipeline_yaml(ROOT / "targets" / issue.repo, issue).get("components") or {}
        comp: Any = comps.get(issue.component) or next(iter(comps.values()), None)
        declared = comp.get("owner") if comp else None
    except (OSError, RuntimeError, StopIteration, AttributeError):
        declared = None
    return (str(declared), "pipeline.yaml") if declared else ("maintainers", "default")


def oncall_for(catalog: dict[str, Any], team: str) -> str:
    people = catalog["teams"].get(team, {}).get("oncall") or ["unassigned"]
    return str(people[datetime.now(UTC).isocalendar().week % len(people)])


async def auto_triage(state: RunState, deps: Deps) -> dict[str, Any]:
    from debugassist.mcp_servers import code_search

    issue = state.issue
    assert issue
    frames: list[dict[str, Any]] = issue.latest_event.get("frames") or []
    top = top_in_app(frames)
    owner_team, owner_source = None, "clef"
    if top and top.get("file"):
        owners = code_search.codeowners_for(issue.repo, str(top["file"]))
        owner_team = owners.get("team")
        owner_source = "codeowners" if owner_team else "clef"
    real_repo = issue.source == "github"
    if real_repo and owner_team is None:
        # A real repository has its own maintainers, not a MiniRide team (ROADMAP-100 077): its CODEOWNERS
        # default rule, else the owner its pipeline.yaml names, else "maintainers".
        owner_team, owner_source = repo_owner(issue)
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
        oncall=team if real_repo else oncall_for(deps.catalog, team),
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
            dup_label = jira_label(triage.duplicate_of)
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
            f"Opened automatically from {source_label(issue)} {issue.id} "
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
        ("para", f"{source_label(issue)}: {issue.url}"),
        ("para", f"DebugAssist run {state.run_id} is investigating."),
    ]
    verdict = deps.gate.verdict("jira.create_issue")
    label = jira_label(issue.id)
    if verdict is Verdict.LIVE:
        ticket = deps.jira.find_open(label)  # one ticket per Vitals issue: reuse it on re-runs
        if ticket:
            found = ticket
            deps.gate.gated(
                "jira.comment",
                lambda: deps.jira.comment(
                    found.key, [("para", f"DebugAssist run {state.run_id} picked this up again.")]
                ),
                run_id=state.run_id,
                detail={"key": found.key},
            )
        else:
            ticket = deps.jira.create(
                f"[{priority}] {issue.title[:180]}",
                blocks,
                priority,
                ["bug", "debugassist", issue.app, label],
            )
        opened = ticket
        deps.gate.gated(
            "jira.transition",
            lambda: deps.jira.transition(opened.key, "In Progress"),
            run_id=state.run_id,
            detail={"key": opened.key, "to": "In Progress"},
        )
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
            links={source_label(issue): issue.url, "Jira": triage.jira_url or ""},
            fields={"App": f"{issue.app} {issue.last_version}", "Ticket": triage.jira_key or "-"},
        )
        notes.append(notify(deps, state.run_id, msg))
    return {"triage": triage, "decisions": decisions, "notifications": notes}
