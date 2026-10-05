"""Root-cause analysis around the RCA agent (N3): Clef decides, LLM agents reason, code fetches.

* D10 routes the RCA agent's reasoning effort by difficulty.
* D6 runs a short evidence loop *before* the agent: need more data? from which source? (fetch is code).
* D7 picks specialised subagents (configs/subagents.yaml); they run in parallel on pruned inputs and
  return findings with evidence ids that the RCA agent consolidates.
* D8 watches the RCA agent's trajectory every few tool calls (warn or stop early; max_turns stays).
* D9 checks every RCA claim against the evidence it cites: kept, flagged unverified, or dropped.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Any

import httpx
import yaml

from debugassist.core import tracing, untrusted
from debugassist.core.evidence import EvidenceItem, evidence_id
from debugassist.core.policy import ROOT
from debugassist.decisions.engine import RunContext
from debugassist.decisions.state import CompactState
from debugassist.llm.spec import LLMNodeSpec, LLMResult, ToolCall
from debugassist.pipeline import collector
from debugassist.pipeline.deps import Deps
from debugassist.pipeline.state import Claim, Finding, Issue, RCAOutput, RunState

MAX_EVIDENCE_ROUNDS = 2
GROUNDING_CHARS = 6_000  # per cited item; each D9 call carries only one claim's citations
SUBAGENT_EVIDENCE_TOKENS = 5_000

SUBAGENT_PROMPT = """You are the {sid} subagent in an automated debugging pipeline for MiniRide (a ride-hailing
app: React client, Node GraphQL gateway, Python dispatch, Go payments). Role: {description}.

Focus: {focus}

You get only the evidence relevant to your role; every item has an evidence id (ev_…) and tool results
carry one too. Work fast (you have very few turns): check what your evidence shows, use a tool only to
settle something specific, then call submit_result. Every fact must cite the evidence ids it rests on;
never cite an id you did not see. If your evidence does not bear on the issue, say so in the summary
with low confidence — that is a useful answer."""


@cache
def subagent_config() -> dict[str, Any]:
    return yaml.safe_load((ROOT / "configs" / "subagents.yaml").read_text())


def _ctx(state: RunState) -> RunContext:
    assert state.issue
    return RunContext(run_id=state.run_id, issue_id=state.issue.id)


def _bundle(items: list[EvidenceItem], budget_tokens: int) -> str:
    parts: list[str] = []
    used = 0
    for it in items:
        body = json.dumps(it.data, default=str)
        chunk = f"### {it.id} — {it.summary}\n{body[:6000]}\n"
        cost = int(len(chunk) / 3.5)
        if used + cost > budget_tokens:
            parts.append(f"### {it.id} — {it.summary}\n(omitted for size; fetch with tools if needed)\n")
            continue
        parts.append(chunk)
        used += cost
    return "\n".join(parts)


# ---- D10 --------------------------------------------------------------------------------------


async def route_effort(state: RunState, deps: Deps) -> tuple[str, dict[str, Any], str | None]:
    assert state.issue
    cs = (
        CompactState()
        .add("issue", collector.issue_summary(state.issue), priority=0)
        .add("evidence", [e.summary for e in state.evidence], priority=1)
    )
    d = await deps.engine.decide("D10", cs, ctx=_ctx(state))
    effort = {"effort_low": "low", "effort_medium": "medium", "effort_high": "high"}.get(
        d.action or "", "high"
    )
    return (
        effort,
        {"difficulty": d.chosen.get("difficulty"), "p": d.p, "band": d.band, "effort": effort},
        d.ledger_id,
    )


# ---- D6 ---------------------------------------------------------------------------------------


Fetcher = Callable[[], EvidenceItem | None]


def _event_time(issue: Issue) -> datetime | None:
    ts = issue.latest_event.get("ts") or issue.report.get("created_at")
    if isinstance(ts, int | float):
        return datetime.fromtimestamp(float(ts), UTC)
    if isinstance(ts, str) and ts:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return None


def _related_reports(issue: Issue, deps: Deps) -> EvidenceItem | None:
    """BugDrop reports for the same app version within ±3 h of the event (what users said)."""
    from debugassist.mcp_servers import bug_reports as br

    at = _event_time(issue)
    reports = httpx.get(f"{deps.bugdrop_url}/api/reports", params={"app_name": issue.app}, timeout=15).json()
    near = [
        r
        for r in reports
        if r["id"] != issue.id
        and r.get("version") == issue.version
        and (
            at is None
            or abs(datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) - at) <= timedelta(hours=3)
        )
    ][:2]
    if not near:
        return None
    data = {
        "kind": "related_reports",
        "reports": [
            {**br.get_report(r["id"]), "ui_state_timeline": br.get_ui_state_timeline(r["id"])} for r in near
        ],
    }
    data["evidence_id"] = evidence_id("bugdrop", data)
    return collector.ev(
        "bugdrop", data, f"Related BugDrop reports on {issue.version}: {', '.join(r['id'] for r in near)}"
    )


def _related_vitals(issue: Issue, deps: Deps) -> EvidenceItem | None:
    """Open Vitals issues for the same app version (crashes, hangs, perf) — what the app recorded."""
    from debugassist.mcp_servers import crash_analytics as ca

    issues = httpx.get(f"{deps.vitals_url}/api/issues", params={"status": "open"}, timeout=15).json()
    near = [i for i in issues if i["id"] != issue.id and i.get("app") == issue.app][:2]
    if not near:
        return None
    data = {"kind": "related_vitals", "issues": [ca.get_issue(i["id"]) for i in near]}
    data["evidence_id"] = evidence_id("vitals", data)
    return collector.ev(
        "vitals", data, f"Related Vitals issues: {', '.join(i['id'] + ' ' + i['title'][:50] for i in near)}"
    )


def fetchers(issue: Issue, deps: Deps) -> dict[str, tuple[str, Fetcher]]:
    """Sources D6 can ask for — each fetch is deterministic code."""
    from debugassist.mcp_servers import incidents as inc
    from debugassist.mcp_servers import logging_ as lg
    from debugassist.mcp_servers import metrics_profiles as mp
    from debugassist.mcp_servers import releases as rel

    at = _event_time(issue)
    around = at.isoformat() if at else None
    out: dict[str, tuple[str, Fetcher]] = {
        "related_reports": (
            "what users reported in BugDrop near the event",
            lambda: _related_reports(issue, deps),
        ),
        "related_vitals": (
            "other crashes/hangs/perf issues Vitals recorded for this app",
            lambda: _related_vitals(issue, deps),
        ),
        "incidents": (
            "active incidents and third-party outages",
            lambda: collector.ev("incident", inc.list_active_incidents(), "Declared incidents still active"),
        ),
    }
    for svc in collector.LOG_SERVICES:
        out[f"logs_{svc}"] = (
            f"{svc} logs around the event",
            lambda svc=svc: collector.ev(
                "logs",
                lg.query_logs(service=svc, minutes=20, around=around, limit=20),
                f"{svc} logs in the 20 minutes around the event",
            ),
        )
    session = issue.session_id or issue.latest_event.get("session_id")
    if session:
        out["session_perf"] = (
            "client CPU, timer wakeups and long tasks for the session",
            lambda: collector.ev(
                "metrics", mp.session_perf(str(session)), "Client performance samples from the session"
            ),
        )
    if issue.source == "vitals":
        out["last_good_first_bad"] = (
            "the last good and first bad release",
            lambda: collector.ev(
                "releases",
                rel.last_good_and_first_bad(issue.id),
                "Last good and first bad release for the issue",
            ),
        )
    return out


async def evidence_loop(
    state: RunState, deps: Deps
) -> tuple[list[EvidenceItem], list[dict[str, Any]], list[str]]:
    """D6, at most MAX_EVIDENCE_ROUNDS: ask Clef whether more evidence is needed and from where; fetch it."""
    issue = state.issue
    assert issue
    avail = fetchers(issue, deps)
    have = {e.id for e in state.evidence}
    added: list[EvidenceItem] = []
    rounds: list[dict[str, Any]] = []
    ledgers: list[str] = []
    for n in range(MAX_EVIDENCE_ROUNDS):
        if not avail:
            break
        cs = (
            CompactState()
            .add("issue", collector.issue_summary(issue), priority=0)
            .add("category", (state.rca.category_decision if state.rca else {}), priority=1)
            .add("evidence_so_far", [e.summary for e in [*state.evidence, *added]], priority=1)
        )
        sources = [{"id": k, "description": v[0]} for k, v in avail.items()]
        d = await deps.engine.decide("D06", cs, params={"sources": sources}, ctx=_ctx(state))
        ledgers.append(d.ledger_id or "")
        choice = str(d.chosen.get("next_source", ""))
        rec: dict[str, Any] = {"round": n + 1, "need_more_p": d.p, "action": d.action, "source": choice}
        if d.action != "fetch_more" or choice not in avail:
            rounds.append(rec)
            break
        _, fetch = avail.pop(choice)
        notes: list[str] = []
        item = collector._try(notes, choice, fetch)  # pyright: ignore[reportPrivateUsage]
        if item is not None and item.id not in have:
            added.append(item)
            have.add(item.id)
            rec["added"] = item.summary
        else:
            rec["added"] = None if not notes else f"failed: {notes[0]}"
        rounds.append(rec)
    return added, rounds, ledgers


# ---- D7 + subagents ---------------------------------------------------------------------------


def subagent_pool(state: RunState, deps: Deps) -> dict[str, dict[str, Any]]:
    """The subagents D7 may choose from: the platform's (configs/subagents.yaml) plus those of the issue's
    domains (marketplace/domains), filtered by the agent type's allow list, its preferred ones first."""
    from debugassist.harness import domains
    from debugassist.pipeline import skills

    issue = state.issue
    assert issue
    pool: dict[str, dict[str, Any]] = dict(subagent_config()["subagents"])
    root = skills.root_for(deps.agent_type)
    pool.update(domains.subagents(domains.for_issue(root, issue.repo, issue.component)))
    prefs: dict[str, list[str]] = deps.agent_type.get("subagents") or {}
    allow = prefs.get("allow") or []
    prefer = prefs.get("prefer") or []
    if allow:
        pool = {k: v for k, v in pool.items() if k in allow or "domain" in v}
    ordered = [k for k in prefer if k in pool] + [k for k in pool if k not in prefer]
    return {k: pool[k] for k in ordered}


async def pick_subagents(state: RunState, deps: Deps) -> tuple[list[str], dict[str, float], str | None]:
    assert state.issue
    cfg = subagent_config()
    subs = [{"id": sid, "description": s["description"]} for sid, s in subagent_pool(state, deps).items()]
    cs = (
        CompactState()
        .add("issue", collector.issue_summary(state.issue), priority=0)
        .add("evidence", [e.summary for e in state.evidence], priority=1)
    )
    d = await deps.engine.decide("D07", cs, params={"subagents": subs}, ctx=_ctx(state))
    ps = {sid: float(v.p) for sid, v in d.items.items()}
    spawn = sorted((s for s, v in d.items.items() if v.action == "spawn"), key=lambda s: -ps[s])
    maybe = sorted((s for s, v in d.items.items() if v.action == "spawn_if_budget"), key=lambda s: -ps[s])
    return [*spawn, *maybe][: int(cfg.get("max_parallel", 4))], ps, d.ledger_id


async def run_subagent(
    sid: str, state: RunState, deps: Deps, mcp_env: dict[str, str]
) -> tuple[dict[str, Any], LLMResult]:
    assert state.issue
    cfg = subagent_config()
    s = subagent_pool(state, deps)[sid]
    from debugassist.pipeline import budget

    limits = budget.cap({**cfg["defaults"], **{k: v for k, v in s.items() if k in cfg["defaults"]}}, deps)
    inputs = [e for e in state.evidence if e.source in s["inputs"]]
    spec = LLMNodeSpec(
        node=f"subagent_{sid}",
        system_prompt=SUBAGENT_PROMPT.format(
            sid=sid, description=s["description"], focus=" ".join(s["focus"].split())
        ),
        mcp_servers=s["mcp_servers"],
        **limits,
    )
    prompt = (
        f"Issue: {json.dumps(collector.issue_summary(state.issue), default=str)}\n\n"
        f"Your evidence ({len(inputs)} items):\n"
        + (
            untrusted.fence("collected evidence", b)
            if (b := _bundle(inputs, SUBAGENT_EVIDENCE_TOKENS))
            else "(none — use your tools)"
        )
        + "\n\n"
        "Report your findings with submit_result."
    )
    with tracing.span(f"subagent {sid}", kind="agent", subagent=sid, domain=s.get("domain")):
        r = await deps.runner().run(spec, prompt, Finding, mcp_env=mcp_env)
    finding = Finding.model_validate(r.output) if r.output else None
    record: dict[str, Any] = {
        "id": sid,
        "status": r.status,
        "turns": r.turns,
        "cost_usd": r.cost_usd,
        "inputs": len(inputs),
        "finding": finding.model_dump() if finding else None,
        "error": (r.error or "")[:200] or None,
    }
    return record, r


async def fan_out(
    state: RunState, deps: Deps, mcp_env: dict[str, str]
) -> tuple[list[dict[str, Any]], list[LLMResult], list[str]]:
    chosen, ps, ledger = await pick_subagents(state, deps)
    if not chosen:
        return [], [], [ledger or ""]
    results = await asyncio.gather(
        *(run_subagent(sid, state, deps, mcp_env) for sid in chosen), return_exceptions=True
    )
    records: list[dict[str, Any]] = []
    raw: list[LLMResult] = []
    for sid, res in zip(chosen, results, strict=True):
        if isinstance(res, BaseException):
            records.append(
                {
                    "id": sid,
                    "status": "error",
                    "error": f"{type(res).__name__}: {str(res)[:160]}",
                    "p": ps.get(sid),
                }
            )
            continue
        rec, r = res
        records.append({**rec, "p": round(ps.get(sid, 0.0), 3)})
        raw.append(r)
    return records, raw, [ledger or ""]


def findings_text(records: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for rec in records:
        f = rec.get("finding")
        if not f:
            lines.append(f"- {rec['id']}: no finding ({rec.get('status')})")
            continue
        lines.append(f"- {rec['id']} ({f['confidence']} confidence): {f['summary']}")
        for fact in f.get("facts", [])[:6]:
            lines.append(f"    · {fact['text']} [{', '.join(fact.get('evidence_ids', []))}]")
    return "\n".join(lines)


# ---- D8 ---------------------------------------------------------------------------------------


def make_monitor(
    state: RunState, deps: Deps, ledgers: list[str]
) -> Callable[[list[ToolCall]], Awaitable[str]]:
    assert state.issue
    summary = {"title": state.issue.title, "kind": state.issue.kind}

    async def monitor(calls: list[ToolCall]) -> str:
        trajectory = [
            f"{c.name}({', '.join(str(v)[:50] for v in c.args.values())}) → {'ok' if c.ok else 'failed'}: {c.result_preview[:120]}"
            for c in calls
        ]
        cs = CompactState().add("issue", summary, priority=0).add("recent_tool_calls", trajectory, priority=0)
        d = await deps.engine.decide("D08", cs, ctx=_ctx(state))
        ledgers.append(d.ledger_id or "")
        return d.action or "continue"

    return monitor


# ---- D9 ---------------------------------------------------------------------------------------


def evidence_lookup(state: RunState, results: list[LLMResult]) -> dict[str, str]:
    """Everything citable: collected evidence, plus what tools returned during the agents' runs."""
    out = {e.id: f"{e.summary}\n{json.dumps(e.data, default=str)[:GROUNDING_CHARS]}" for e in state.evidence}
    for r in results:
        for c in r.tool_calls:
            if c.evidence_id and c.evidence_id not in out:
                out[c.evidence_id] = (
                    f"{c.name} result: {(c.evidence_text or c.result_preview)[:GROUNDING_CHARS]}"
                )
    return out


async def ground_claims(
    state: RunState, deps: Deps, output: RCAOutput, lookup: dict[str, str]
) -> tuple[RCAOutput, list[dict[str, Any]], list[Claim], list[str]]:
    """One Clef call per claim, each seeing only the evidence that claim cites.

    Batching every claim with all cited evidence into one state made Clef lose track of which evidence
    belonged to which claim (true claims scored 0.03-0.27 in a live run; the same claims alone scored
    0.87-0.99, and a false control 0.007). Citations of ids no source ever returned are dropped without
    a model call.
    """
    if not output.claims:
        return output, [], [], []

    async def one(i: int, c: Claim) -> tuple[str, float | None, str | None]:
        known = [eid for eid in c.evidence_ids if eid in lookup]
        if not known:
            return "unsupported", None, None  # cites nothing that exists: fabricated or missing citations
        cs = CompactState().add("cited_evidence", {eid: lookup[eid] for eid in known}, priority=0)
        claim = {"id": f"c{i + 1}", "text": c.text, "citations": ", ".join(known)}
        d = await deps.engine.decide("D09", cs, params={"claims": [claim]}, ctx=_ctx(state))
        v = d.items.get(f"c{i + 1}")
        label = {"keep": "supported", "flag_unverified": "unverified", "drop": "unsupported"}.get(
            v.action if v else "", "unverified"
        )
        return label, (round(v.p, 3) if v else None), d.ledger_id

    results = await asyncio.gather(*(one(i, c) for i, c in enumerate(output.claims)))
    verdicts: list[dict[str, Any]] = []
    kept: list[Claim] = []
    dropped: list[Claim] = []
    ledgers: list[str] = []
    for i, (c, (label, p, ledger)) in enumerate(zip(output.claims, results, strict=True)):
        verdicts.append({"claim": i, "text": c.text, "grounding": label, "p": p})
        (dropped if label == "unsupported" else kept).append(c)
        if ledger:
            ledgers.append(ledger)
    return output.model_copy(update={"claims": kept}), verdicts, dropped, ledgers
