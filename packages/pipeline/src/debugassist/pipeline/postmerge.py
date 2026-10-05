"""Post-merge watch (N9 + D17): after the fix is merged and deployed, did the issue go away?

`post_merge_watch` (the last graph node) records what to watch and leaves the run in `watching`.
`debugassist watch <run>` checks later, deterministically:

1. merged? (GitHub, when live; a local deploy of the bot branch stands in for the merge otherwise)
2. deployed? (`make deploy` records `.data/deploys.jsonl`)
3. enough traffic since the deploy? (sessions in Vitals)
4. the issue's rate before vs after the deploy, over windows of equal length: affected sessions per
   session for a Vitals issue; BugDrop reports per session for a report.

Clef (D17) decides resolved / keep watching / reopen from those numbers; code acts: resolve the Vitals
issue or BugDrop report, move the Jira ticket, restore a rolled-back flag (policy-gated), post to chat.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from debugassist.core.policy import ROOT, Verdict
from debugassist.decisions.engine import RunContext
from debugassist.decisions.state import CompactState
from debugassist.integrations.chat import ChatMessage
from debugassist.pipeline import collector
from debugassist.pipeline.deps import Deps
from debugassist.pipeline.state import RunState, Watch

DEPLOYS = ROOT / ".data" / "deploys.jsonl"
MIN_SESSIONS = 20
MIN_WINDOW = timedelta(minutes=15)
MAX_WINDOW = timedelta(hours=24)


def start(state: RunState) -> Watch | None:
    if not state.pr:
        return None
    return Watch(pr_url=state.pr.url, pr_number=state.pr.number, started_at=datetime.now(UTC).isoformat())


def _deploy_after(repo: str, after: str) -> dict[str, Any] | None:
    if not DEPLOYS.is_file():
        return None
    rows = [json.loads(line) for line in DEPLOYS.read_text().splitlines() if line.strip()]
    rows = [r for r in rows if r["repo"] == repo and r["at"] > after]
    return rows[-1] if rows else None


def windows(
    deployed_at: datetime, now: datetime
) -> tuple[tuple[datetime, datetime], tuple[datetime, datetime]]:
    """Equal-length windows either side of the deploy (at least 15 min, at most 24 h)."""
    length = min(max(now - deployed_at, MIN_WINDOW), MAX_WINDOW)
    return (deployed_at - length, deployed_at), (deployed_at, deployed_at + length)


def _vitals_stats(deps: Deps, since: datetime, until: datetime, fingerprint: str | None) -> dict[str, Any]:
    params: dict[str, str] = {"since": since.isoformat(), "until": until.isoformat()}
    if fingerprint:
        params["fingerprint"] = fingerprint
    return httpx.get(f"{deps.vitals_url}/api/stats", params=params, timeout=15).raise_for_status().json()


def measure(deps: Deps, state: RunState, since: datetime, until: datetime) -> dict[str, Any]:
    issue = state.issue
    assert issue
    if issue.source == "vitals":
        return _vitals_stats(deps, since, until, issue.fingerprint)
    stats = _vitals_stats(deps, since, until, None)
    reports = (
        httpx.get(
            f"{deps.bugdrop_url}/api/reports",
            params={"app_name": issue.app, "since": since.isoformat(), "limit": 200},
            timeout=15,
        )
        .raise_for_status()
        .json()
    )
    n = sum(1 for r in reports if datetime.fromisoformat(r["created_at"]) < until)
    return {**stats, "reports": n, "rate": round(n / stats["sessions"], 4) if stats["sessions"] else None}


async def check(
    state: RunState, deps: Deps, *, min_sessions: int = MIN_SESSIONS, approve_flag_restore: bool = False
) -> Watch:
    issue, w = state.issue, state.watch
    assert issue and w
    now = datetime.now(UTC)
    w.checks += 1
    w.last_checked = now.isoformat()
    if (
        w.pr_number is not None
        and issue.gh_repo
        and (merged := deps.github.merged(issue.gh_repo, w.pr_number)) is not None
    ):
        w.merged = merged
        if not merged:
            w.reason = "PR not merged yet"
            return w
    deploy = _deploy_after(issue.repo, w.started_at)
    if deploy is None:
        w.reason = "not deployed yet (make deploy REF=<merged branch>)"
        return w
    w.deploy = deploy
    deployed_at = datetime.fromisoformat(deploy["at"])
    (b0, b1), (a0, a1) = windows(deployed_at, now)
    w.before, w.after = measure(deps, state, b0, b1), measure(deps, state, a0, min(a1, now))
    if w.after.get("sessions", 0) < min_sessions:
        w.reason = (
            f"not enough traffic since the deploy: {w.after.get('sessions', 0)} of {min_sessions} sessions"
        )
        return w
    cs = (
        CompactState()
        .add("issue", collector.issue_summary(issue), priority=0)
        .add("before_deploy", w.before, priority=0)
        .add("after_deploy", w.after, priority=0)
        .add("deploy", deploy, priority=1)
    )
    d = await deps.engine.decide("D17", cs, ctx=RunContext(run_id=state.run_id, issue_id=issue.id))
    w.decision = {"p": d.p, "band": d.band, "action": d.action, "ledger": d.ledger_id}
    w.reason = None
    if d.action == "close_issue":
        w.status = "resolved"
        w.actions = _resolve(state, deps, approve_flag_restore)
    elif d.action == "reopen_issue":
        w.status = "reopened"
        w.actions = _reopen(state, deps)
    else:
        w.status = "watching"
    return w


def _post(deps: Deps, state: RunState, action: str, url: str, body: dict[str, Any] | None = None) -> str:
    verdict = deps.gate.verdict(action)
    result = "dry_run"
    if verdict is Verdict.LIVE:
        try:
            httpx.post(url, json=body, timeout=10).raise_for_status()
            result = "done"
        except httpx.HTTPError as exc:
            result = f"failed: {type(exc).__name__}"
    deps.gate.record(action, verdict, run_id=state.run_id, detail={"url": url, **(body or {})}, result=result)
    return result


def _resolve(state: RunState, deps: Deps, approve_flag_restore: bool) -> list[str]:
    from debugassist.mcp_servers import feature_flags as ff

    issue, tr, m, w = state.issue, state.triage, state.mitigation, state.watch
    assert issue and w
    done: list[str] = []
    if issue.source == "vitals":
        done.append(
            f"vitals resolve: {_post(deps, state, 'source.resolve', f'{deps.vitals_url}/api/issues/{issue.id}/resolve')}"
        )
    elif issue.source == "bugdrop":
        r = _post(
            deps,
            state,
            "source.resolve",
            f"{deps.bugdrop_url}/api/reports/{issue.id}/status",
            {"status": "resolved"},
        )
        done.append(f"bugdrop resolved: {r}")
    if tr and tr.jira_key:
        done.append(
            _jira(
                deps,
                tr.jira_key,
                f"Resolved after deploy: {_rates(w)}. (DebugAssist post-merge watch)",
                "Done",
            )
        )
    if m and m.flag and m.action == "rolled_back" and m.rolled_back_from:
        verdict = deps.gate.verdict("flags.restore")
        live = verdict is Verdict.LIVE or (verdict is Verdict.APPROVAL and approve_flag_restore)
        res = ff.rollback_flag(
            m.flag, m.rolled_back_from, reason=f"{issue.id}: fix deployed and verified", dry_run=not live
        )
        deps.gate.record(
            "flags.restore",
            Verdict.LIVE if live else Verdict.DRY_RUN,
            run_id=state.run_id,
            detail={"flag": m.flag, "to": m.rolled_back_from},
            result=res,
        )
        done.append(
            f"flag {m.flag} → {m.rolled_back_from}% ({'applied' if res.get('applied') else 'dry run'})"
        )
    done.append(
        _chat(deps, state, "success", f"Resolved: {issue.title[:180]}", f"After the deploy: {_rates(w)}.")
    )
    return done


def _reopen(state: RunState, deps: Deps) -> list[str]:
    issue, tr, w = state.issue, state.triage, state.watch
    assert issue and w
    done: list[str] = []
    if tr and tr.jira_key:
        done.append(
            _jira(
                deps,
                tr.jira_key,
                f"Still happening after the deploy: {_rates(w)}. Reopening. (DebugAssist)",
                "In Progress",
            )
        )
    if issue.source == "bugdrop":
        r = _post(
            deps,
            state,
            "source.resolve",
            f"{deps.bugdrop_url}/api/reports/{issue.id}/status",
            {"status": "in_progress"},
        )
        done.append(f"bugdrop in_progress: {r}")
    done.append(
        _chat(
            deps,
            state,
            "alert",
            f"Not fixed by the deploy: {issue.title[:170]}",
            f"After the deploy: {_rates(w)}.",
        )
    )
    return done


def _jira(deps: Deps, key: str, text: str, status: str) -> str:
    """Comment and move the ticket; a Jira error is reported, not fatal (the rest still happens)."""
    try:
        deps.jira.comment(key, [("para", text)])
        deps.jira.transition(key, status)
        return f"jira {key} → {status}"
    except httpx.HTTPError as exc:
        return f"jira {key}: failed ({type(exc).__name__})"


def _rates(w: Watch) -> str:
    def fmt(s: dict[str, Any]) -> str:
        what = f"{s.get('reports')} reports" if "reports" in s else f"{s.get('affected_sessions')} affected"
        return f"{what} / {s.get('sessions')} sessions (rate {s.get('rate')})"

    return f"before {fmt(w.before)} → after {fmt(w.after)}"


def _chat(deps: Deps, state: RunState, level: str, title: str, text: str) -> str:
    from debugassist.pipeline.nodes import _notify  # pyright: ignore[reportPrivateUsage]

    issue, tr = state.issue, state.triage
    assert issue
    msg = ChatMessage(
        to=f"@{tr.oncall}" if tr else "#debugassist",
        title=title,
        text=text,
        level=level,  # pyright: ignore[reportArgumentType]
        links={
            "PR": state.pr.url if state.pr else "",
            "Jira": (tr.jira_url if tr else None) or "",
            "Issue": issue.url,
        },
    )
    r = _notify(deps, state.run_id, msg)
    return f"chat: {r.get('mode')}"
