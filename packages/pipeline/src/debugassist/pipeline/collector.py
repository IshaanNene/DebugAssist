"""Context collection (N2) and the pieces of triage that need the sources (N1): deterministic, not an LLM.

* `ingest_bugdrop` turns a BugDrop report into an `Issue`.
* `dedup_candidates` lists open issues and recent reports for D2.
* `collect` gathers evidence: **core** items always go to the RCA; **optional** windows (logs around the
  event, the session, traces, perf samples, incidents, adoption, report log rings) are scored by Clef-flash
  (D3) and kept in order of relevance until the evidence token budget is used. Screenshots get the D4
  vision questions. Every source call is isolated: one failing source never stops the collection.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from debugassist.core.evidence import EvidenceItem, Source
from debugassist.decisions.engine import RunContext
from debugassist.decisions.state import CompactState
from debugassist.pipeline.deps import APPS, Deps
from debugassist.pipeline.state import Issue, RunState

log = logging.getLogger(__name__)
EVIDENCE_BUDGET_TOKENS = 12_000  # what the RCA agent gets in its prompt (core + kept optional windows)
LOG_SERVICES = ("gateway", "dispatch", "payments")


def ev(source: Source, data: dict[str, Any], summary: str) -> EvidenceItem:
    return EvidenceItem(
        id=data["evidence_id"], source=source, kind=data.get("kind", source), summary=summary, data=data
    )


def tokens(item: EvidenceItem) -> int:
    return int(len(json.dumps(item.data, default=str)) / 3.5) + 20


def _try(notes: list[str], what: str, fn: Callable[[], EvidenceItem | None]) -> EvidenceItem | None:
    try:
        return fn()
    except Exception as exc:  # a source being down is a note, not a failed run
        notes.append(f"{what}: {type(exc).__name__}: {str(exc)[:120]}")
        return None


# ---- ingest + dedup --------------------------------------------------------------------------


async def ingest_bugdrop(ref: str, deps: Deps) -> Issue:
    async with httpx.AsyncClient(base_url=deps.bugdrop_url, timeout=15) as http:
        r = (await http.get(f"/api/reports/{ref.upper()}")).raise_for_status().json()
    repo, gh_repo, component, language = APPS[r["app"]]
    device: dict[str, Any] = r.get("device") or {}
    title = " ".join((r.get("description") or "bug report").split())
    return Issue(
        source="bugdrop",
        id=r["id"],
        url=f"{deps.bugdrop_ui}/reports/{r['id']}",
        title=title[:160],
        kind="bug_report",
        app=r["app"],
        platform=str(device.get("os") or "web"),
        version=r.get("version") or "unknown",
        first_version=r.get("version") or "unknown",
        last_version=r.get("version") or "unknown",
        events=1,
        repo=repo,
        gh_repo=gh_repo,
        component=component,
        language=language,
        session_id=r.get("session_id"),
        report={
            k: r.get(k)
            for k in (
                "description",
                "created_at",
                "device",
                "city",
                "route",
                "flags",
                "network",
                "log_counts",
                "files",
            )
        },
    )


async def dedup_candidates(issue: Issue, deps: Deps, k: int = 8) -> list[dict[str, str]]:
    """Open Vitals issues and recent BugDrop reports for the same app, newest first (D2's options)."""
    out: list[dict[str, str]] = []
    async with httpx.AsyncClient(timeout=15) as http:
        try:
            issues = (await http.get(f"{deps.vitals_url}/api/issues", params={"status": "open"})).json()
            for i in issues:
                if i["id"] != issue.id and i.get("app") == issue.app:
                    out.append({"id": i["id"], "description": f"Vitals {i.get('kind')}: {i['title']}"})
        except httpx.HTTPError:
            pass
        try:
            since = (datetime.now(UTC) - timedelta(days=7)).isoformat()
            reports = (
                await http.get(
                    f"{deps.bugdrop_url}/api/reports", params={"app_name": issue.app, "since": since}
                )
            ).json()
            for r in reports:
                if r["id"] != issue.id:
                    text = " ".join((r.get("description") or "").split())[:200]
                    out.append(
                        {"id": r["id"], "description": f"BugDrop report (v{r.get('version')}): {text}"}
                    )
        except httpx.HTTPError:
            pass
    return out[:k]


def issue_summary(issue: Issue) -> dict[str, Any]:
    frames: list[dict[str, Any]] = issue.latest_event.get("frames") or []
    out: dict[str, Any] = {
        "id": issue.id,
        "source": issue.source,
        "kind": issue.kind,
        "title": issue.title,
        "app": issue.app,
    }
    out["versions"] = f"{issue.first_version}→{issue.last_version}"
    if frames:
        out["stack"] = [f"{f['function']} ({f['file']}:{f.get('line')})" for f in reversed(frames[-6:])]
    if issue.report:
        out["report"] = {k: issue.report.get(k) for k in ("description", "route", "flags", "network", "city")}
    return out


# ---- evidence ---------------------------------------------------------------------------------


def _event_time(issue: Issue) -> str | None:
    ts = issue.latest_event.get("ts") or issue.report.get("created_at")
    if isinstance(ts, int | float):
        return datetime.fromtimestamp(float(ts), UTC).isoformat()
    return str(ts) if ts else None


def vitals_core(issue: Issue, notes: list[str]) -> list[EvidenceItem]:
    """The crash itself, flag exposure, the release window and the code at the crash site — always kept."""
    from debugassist.mcp_servers import code_search
    from debugassist.mcp_servers import crash_analytics as ca
    from debugassist.mcp_servers import feature_flags as ff
    from debugassist.mcp_servers import git_history as gh

    assert issue.fingerprint
    fp = issue.fingerprint
    items: list[EvidenceItem | None] = []

    def group() -> EvidenceItem:
        g = ca.get_crash_group(fp, events=5)
        return ev(
            "vitals",
            g,
            f"Crash group: {g['group']['count']} events, {g['group']['first_version']}→{g['group']['last_version']}, latest stacks and breadcrumbs",
        )

    items.append(_try(notes, "crash group", group))
    fe = ca.flag_exposure(fp)
    items.append(ev("vitals", fe, "Feature-flag exposure among all vs affected sessions"))
    items.append(
        _try(
            notes,
            "versions",
            lambda: ev("vitals", ca.distribution(fp, by="version"), "Affected sessions by app version"),
        )
    )
    for f in fe["flags"]:
        if f["exposed_share_of_affected"] >= 0.5:
            name = f["flag"]

            def corr(flag: str = name) -> EvidenceItem:
                c = ff.flag_crash_correlation(fp, flag)
                return ev("flags", c, f"Crash rate with {flag} on vs off (z={c['z']}, p={c['p_value']:.2g})")

            items.append(_try(notes, f"flag correlation {name}", corr))
            items.append(
                _try(
                    notes,
                    f"flag {name}",
                    lambda flag=name: ev("flags", ff.get_flag(flag), f"Current rollout of {flag}"),
                )
            )
    # Releases: last good and first bad, history filtered to the modules in the stack (pruned input).
    tags = [t["tag"] for t in gh.list_tags(issue.repo, limit=100)["tags"]]
    first_bad = f"v{issue.first_version}"
    last_good = gh.previous_release(issue.repo, first_bad)["previous_release"] if first_bad in tags else None
    frames: list[dict[str, Any]] = issue.latest_event.get("frames") or []
    prefix = "" if issue.component == "." else f"{issue.component}/"
    suspects = sorted(
        {
            prefix + str(f["file"]).removeprefix(prefix)
            for f in frames
            if f.get("in_app", True) and f.get("file") and "vendor/" not in str(f["file"])
        }
    )
    if last_good:
        dirs = sorted({s.rsplit("/", 1)[0] for s in suspects}) or None
        commits = gh.commits_between(issue.repo, last_good, first_bad, dirs)
        items.append(
            ev("git", commits, f"Commits {last_good}..{first_bad} touching {', '.join(dirs or ['all'])}")
        )
        cands = gh.bisect_candidates(issue.repo, last_good, first_bad, suspects)
        items.append(ev("git", cands, "Commits in the window ranked by overlap with files in the stack"))
        if cands["candidates"]:
            top_c = gh.commit_details(issue.repo, cands["candidates"][0]["sha"], max_diff_chars=4000)
            items.append(
                ev("git", top_c, f"Top suspect commit {top_c['sha']}: {top_c['message'].splitlines()[0]}")
            )
    top = next((f for f in reversed(frames) if f.get("in_app", True)), None)
    if top and top.get("file") and top.get("line"):
        path = prefix + str(top["file"]).removeprefix(prefix)
        line = int(top["line"])
        ex = code_search.read_file(issue.repo, path, max(1, line - 20), line + 20)
        if "error" not in ex:
            items.append(
                ev(
                    "code",
                    ex,
                    f"Source around the crashing line {path}:{line} (release v{issue.last_version})",
                )
            )
    return [i for i in items if i is not None]


def bugdrop_core(issue: Issue, notes: list[str]) -> list[EvidenceItem]:
    """The report as filed and its UI-state timeline — always kept."""
    from debugassist.mcp_servers import bug_reports as br

    items = [
        _try(
            notes,
            "report",
            lambda: ev("bugdrop", br.get_report(issue.id), f'The bug report as filed: "{issue.title[:80]}"'),
        ),
        _try(
            notes,
            "ui timeline",
            lambda: ev(
                "bugdrop",
                br.get_ui_state_timeline(issue.id),
                "UI-state timeline: visibility (time hidden) and route changes",
            ),
        ),
    ]
    return [i for i in items if i is not None]


def optional_windows(issue: Issue, notes: list[str]) -> list[EvidenceItem]:
    """Evidence that may or may not matter for this issue; D3 decides what makes the budget."""
    from debugassist.mcp_servers import bug_reports as br
    from debugassist.mcp_servers import crash_analytics as ca
    from debugassist.mcp_servers import incidents as inc
    from debugassist.mcp_servers import logging_ as lg
    from debugassist.mcp_servers import metrics_profiles as mp
    from debugassist.mcp_servers import releases as rel
    from debugassist.mcp_servers import tracing as tr

    out: list[EvidenceItem | None] = []
    at = _event_time(issue)
    if issue.fingerprint:
        for by in ("os", "city"):
            out.append(
                _try(
                    notes,
                    f"by {by}",
                    lambda by=by: ev(
                        "vitals",
                        ca.distribution(issue.fingerprint or "", by=by),
                        f"Affected sessions by {by}",
                    ),
                )
            )
    session = issue.session_id or issue.latest_event.get("session_id")
    if session:
        if issue.source == "vitals":
            out.append(
                _try(
                    notes,
                    "session",
                    lambda: ev(
                        "vitals",
                        ca.get_session(session),
                        "The crashing session: device, flags, events in order",
                    ),
                )
            )
        out.append(
            _try(
                notes,
                "session perf",
                lambda: ev(
                    "metrics",
                    mp.session_perf(session),
                    "Client performance samples from the session (CPU while hidden, wakeups, long tasks)",
                ),
            )
        )
    trace_id = issue.latest_event.get("trace_id")
    if trace_id:
        out.append(
            _try(
                notes,
                "trace",
                lambda: ev(
                    "traces",
                    tr.get_trace(str(trace_id)),
                    "The request trace linked to the latest event (critical path, errors, slowest spans)",
                ),
            )
        )
    for svc in LOG_SERVICES:
        out.append(
            _try(
                notes,
                f"logs {svc}",
                lambda svc=svc: ev(
                    "logs",
                    lg.query_logs(service=svc, minutes=10, around=at, limit=15),
                    f"{svc} logs in the 10 minutes around the event (repeats collapsed, errors first)",
                ),
            )
        )
    out.append(
        _try(
            notes,
            "incidents",
            lambda: ev("incident", inc.list_active_incidents(), "Declared incidents still active"),
        )
    )
    out.append(
        _try(
            notes,
            "dependencies",
            lambda: ev("incident", inc.dependency_status(), "Third-party dependency status"),
        )
    )
    out.append(
        _try(
            notes,
            "adoption",
            lambda: ev("releases", rel.version_adoption(issue.app), f"Version adoption of {issue.app}"),
        )
    )
    if issue.source == "bugdrop":
        for kind in ("console", "graphql", "network", "analytics", "perf"):
            out.append(
                _try(
                    notes,
                    f"report {kind}",
                    lambda kind=kind: ev(
                        "bugdrop", br.get_logs(issue.id, kind, limit=40), f"Report's {kind} log ring"
                    ),
                )
            )
    return [i for i in out if i is not None]


async def screenshot_findings(
    issue: Issue, deps: Deps, ctx: RunContext
) -> tuple[EvidenceItem | None, str | None]:
    """D4: ask Clef the vision questions over the report's images (app screenshot + attachments)."""
    all_files: list[dict[str, Any]] = issue.report.get("files") or []
    files = [f for f in all_files if str(f.get("content_type", "")).startswith("image/")]
    if not files:
        return None, None
    images: list[bytes] = []
    async with httpx.AsyncClient(base_url=deps.bugdrop_url, timeout=20) as http:
        for f in files[:4]:  # Clef accepts at most 4 images
            r = await http.get(f"/api/reports/{issue.id}/files/{f['name']}")
            if r.status_code == 200:
                images.append(r.content)
    if not images:
        return None, None
    state = CompactState().add(
        "report",
        {"description": issue.title, "files": [{k: f.get(k) for k in ("name", "kind")} for f in files[:4]]},
        priority=0,
    )
    d = await deps.engine.decide("D04", state, images=list(images), ctx=ctx)
    ev_id = f"ev_screenshot_d04{(d.ledger_id or '')[:6]}"
    findings: dict[str, Any] = {
        "evidence_id": ev_id,
        "kind": "screenshot_findings",
        "images": [f["name"] for f in files[:4]],
        "blank_screen": round(float(d.probabilities["blank_screen"]["true"]), 3),
        "error_dialog": round(float(d.probabilities["error_dialog"]["true"]), 3),
        "screen": d.chosen.get("screen"),
        "abnormal_battery": round(float(d.probabilities["abnormal_battery"]["true"]), 3),
        "action": d.action,
        "decision": d.ledger_id,
    }
    summary = f"Screenshot findings (Clef D4): screen={findings['screen']}, blank p={findings['blank_screen']}, abnormal battery p={findings['abnormal_battery']}"
    return EvidenceItem(
        id=ev_id,
        source="screenshot",
        kind="screenshot_findings",
        summary=summary,
        data=findings,
    ), d.ledger_id


async def score_and_fit(
    issue: Issue,
    core: list[EvidenceItem],
    optional: list[EvidenceItem],
    deps: Deps,
    ctx: RunContext,
    budget: int = EVIDENCE_BUDGET_TOKENS,
) -> tuple[list[EvidenceItem], list[dict[str, Any]], str | None]:
    """D3: score every optional window, then keep what fits the budget — "keep" first, then "keep if
    budget" by score. Returns kept items, the pruned list (with scores) and the ledger id."""
    if not optional:
        return core, [], None
    windows = [{"id": i.id, "summary": i.summary} for i in optional]
    state = (
        CompactState()
        .add("issue", issue_summary(issue), priority=0)
        .add("core_evidence", [i.summary for i in core], priority=1)
    )
    d = await deps.engine.decide("D03", state, params={"windows": windows}, ctx=ctx)
    score = {i.id: float(d.chosen.get(f"relevance.{i.id}", 0.0)) for i in optional}
    action = {i.id: (d.items[i.id].action if i.id in d.items else "keep_if_budget") for i in optional}
    used = sum(tokens(i) for i in core)
    kept: list[EvidenceItem] = list(core)
    pruned: list[dict[str, Any]] = []
    order = sorted(
        optional, key=lambda i: ({"keep": 0, "keep_if_budget": 1}.get(action[i.id], 2), -score[i.id])
    )
    for it in order:
        cost = tokens(it)
        if action[it.id] in ("keep", "keep_if_budget") and used + cost <= budget:
            kept.append(it)
            used += cost
        else:
            reason = "over budget" if action[it.id] != "drop" else "not relevant"
            pruned.append(
                {
                    "id": it.id,
                    "summary": it.summary,
                    "score": round(score[it.id], 2),
                    "tokens": cost,
                    "reason": reason,
                }
            )
    return kept, pruned, d.ledger_id


async def collect(state: RunState, deps: Deps) -> dict[str, Any]:
    issue = state.issue
    assert issue
    ctx = RunContext(run_id=state.run_id, issue_id=issue.id)
    notes: list[str] = []
    core = vitals_core(issue, notes) if issue.source == "vitals" else bugdrop_core(issue, notes)
    decisions = list(state.decisions)
    shots = None
    if issue.source == "bugdrop":
        shot_item, shot_ledger = await screenshot_findings(issue, deps, ctx)
        if shot_item is not None:
            core.append(shot_item)
            shots = shot_item.data
            decisions.append(shot_ledger or "")
    optional = optional_windows(issue, notes)
    kept, pruned, d3 = await score_and_fit(issue, core, optional, deps, ctx)
    if d3:
        decisions.append(d3)
    if notes:
        log.info("collector notes: %s", notes)
    return {
        "evidence": kept,
        "evidence_pruned": pruned + [{"note": n} for n in notes],
        "screenshots": shots,
        "decisions": decisions,
    }
