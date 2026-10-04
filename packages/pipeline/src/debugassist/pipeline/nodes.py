"""Pipeline nodes N0–N9 (minimal-but-real versions for the walking skeleton).

Deterministic nodes call backends directly (the same functions the MCP servers expose, so evidence
ids match what agents see); LLM nodes go through the LLMRunner seam; decisions go through Clef;
every write goes through the policy gate.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

from debugassist.core.evidence import EvidenceItem, Source
from debugassist.core.policy import ROOT, Verdict
from debugassist.core.settings import Integration, Mode
from debugassist.decisions.engine import RunContext
from debugassist.decisions.state import CompactState
from debugassist.integrations.sandbox import Sandbox
from debugassist.llm.runner import is_daily_quota
from debugassist.llm.spec import LLMNodeSpec, LLMResult
from debugassist.llm.workspace_tools import build_workspace_tools, changed_files, is_test_path
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
    env = {
        "VITALS_URL": "http://localhost:8100",
        "UNLEASH_URL": "http://localhost:4242",
        "CODE_REPOS": json.dumps({state.issue.repo: str(sb.worktree)}),
        "DEBUGASSIST_RUN_ID": state.run_id,
        "DEBUGASSIST_MODE": state.mode,
        "PATH": os.environ.get("PATH", ""),
    }
    return env


def _ev(source: Source, d: dict[str, Any], summary: str) -> EvidenceItem:
    return EvidenceItem(
        id=d["evidence_id"],
        source=source,
        kind=d.get("kind", source),
        summary=summary,  # pyright: ignore[reportArgumentType]
        data={k: v for k, v in d.items() if k not in ("evidence_id", "kind")},
    )


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


def _component_cfg(state: RunState, worktree: Path) -> dict[str, Any]:
    assert state.issue
    cfg = _pipeline_yaml(worktree)["components"]
    if state.issue.component == ".":
        return next(iter(cfg.values()))
    return cfg[state.issue.component]


# ---- N0 ingest ------------------------------------------------------------------------------


async def ingest(state: RunState, deps: Deps) -> dict[str, Any]:
    ref = state.issue_ref
    if not ref.upper().startswith("VIT-"):
        raise ValueError("the walking skeleton ingests Vitals issues (VIT-…); BugDrop reports arrive in P5")
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
    )
    return {"issue": issue}


# ---- N1 auto_triage -------------------------------------------------------------------------


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
    async with httpx.AsyncClient(base_url=deps.vitals_url, timeout=15) as http:
        flags: list[dict[str, Any]] = (
            (await http.get(f"/api/groups/{issue.fingerprint}/flags")).json() if issue.fingerprint else []
        )
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
    # Jira ticket (policy-gated)
    blocks = [
        (
            "para",
            f"Opened automatically from Vitals issue {issue.id} ({issue.events} events, {issue.app} {issue.first_version}→{issue.last_version}).",
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
        ("para", f"Vitals: {issue.url}"),
        ("para", f"DebugAssist run {state.run_id} is investigating."),
    ]
    verdict = deps.gate.verdict("jira.create_issue")
    label = f"vitals-{issue.id.lower()}"
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
        r = deps.slack.message(
            f"@{triage.oncall}",
            f"{priority} {issue.title} — {team} on-call. Jira {triage.jira_key}. DebugAssist is on it.",
            {"vitals": issue.url, "jira": triage.jira_url or ""},
        )
        notes.append({"kind": "slack", "to": triage.oncall, **r})
    return {"triage": triage, "decisions": [*state.decisions, d.ledger_id or ""], "notifications": notes}


# ---- N2 context_collector -------------------------------------------------------------------


async def context_collector(state: RunState, deps: Deps) -> dict[str, Any]:
    from debugassist.mcp_servers import crash_analytics as ca
    from debugassist.mcp_servers import feature_flags as ff
    from debugassist.mcp_servers import git_history as gh

    issue = state.issue
    assert issue and issue.fingerprint
    # The sandbox worktree at the shipped release: code search and the fix both work on it.
    sb = _sandbox(state)
    branch = (
        f"debugassist/{issue.id.lower()}-{re.sub(r'[^a-z0-9]+', '-', issue.title.lower())[:40].strip('-')}"
    )
    if deps.settings.mode(Integration.GITHUB) is not Mode.LIVE:
        branch += "-mock"  # never collide with (and clean up) a live run's worktree for the real PR branch
    sb.create(f"v{issue.last_version}", branch)
    os.environ["CODE_REPOS"] = json.dumps({issue.repo: str(sb.worktree)})

    items: list[EvidenceItem] = []
    group = ca.get_crash_group(issue.fingerprint, events=5)
    items.append(
        _ev(
            "vitals",
            group,
            f"Crash group: {group['group']['count']} events, {group['group']['first_version']}→{group['group']['last_version']}, latest stacks and breadcrumbs",
        )
    )
    fe = ca.flag_exposure(issue.fingerprint)
    items.append(_ev("vitals", fe, "Feature-flag exposure among all vs affected sessions"))
    vd = ca.distribution(issue.fingerprint, by="version")
    items.append(_ev("vitals", vd, "Affected sessions by app version"))
    for by in ("os", "city"):
        dd = ca.distribution(issue.fingerprint, by=by)
        items.append(_ev("vitals", dd, f"Affected sessions by {by}"))
    for f in fe["flags"]:
        if f["exposed_share_of_affected"] >= 0.5:
            corr = ff.flag_crash_correlation(issue.fingerprint, f["flag"])
            items.append(
                _ev(
                    "flags",
                    corr,
                    f"Crash rate with {f['flag']} on vs off (z={corr['z']}, p={corr['p_value']:.2g})",
                )
            )
            items.append(_ev("flags", ff.get_flag(f["flag"]), f"Current rollout of {f['flag']}"))
    # Releases: last good and first bad, history filtered to the modules in the stack (pruned input).
    tags = [t["tag"] for t in gh.list_tags(issue.repo, limit=100)["tags"]]
    first_bad = f"v{issue.first_version}"
    last_good = gh.previous_release(issue.repo, first_bad)["previous_release"] if first_bad in tags else None
    frames: list[dict[str, Any]] = issue.latest_event.get("frames") or []
    comp_prefix = "" if issue.component == "." else f"{issue.component}/"
    suspects = sorted(
        {
            comp_prefix + str(f["file"]).removeprefix(comp_prefix)
            for f in frames
            if f.get("in_app", True) and f.get("file") and "vendor/" not in str(f["file"])
        }
    )
    if last_good and first_bad in tags:
        dirs = sorted({s.rsplit("/", 1)[0] for s in suspects}) or None
        commits = gh.commits_between(issue.repo, last_good, first_bad, dirs)
        items.append(
            _ev("git", commits, f"Commits {last_good}..{first_bad} touching {', '.join(dirs or ['all'])}")
        )
        cands = gh.bisect_candidates(issue.repo, last_good, first_bad, suspects)
        items.append(_ev("git", cands, "Commits in the window ranked by overlap with files in the stack"))
        if cands["candidates"]:
            top_c = gh.commit_details(issue.repo, cands["candidates"][0]["sha"], max_diff_chars=4000)
            items.append(
                _ev("git", top_c, f"Top suspect commit {top_c['sha']}: {top_c['message'].splitlines()[0]}")
            )
    top = _top_in_app(frames)
    if top and top.get("file") and top.get("line"):
        from debugassist.mcp_servers import code_search

        path = comp_prefix + str(top["file"]).removeprefix(comp_prefix)
        line = int(top["line"])
        ex = code_search.read_file(issue.repo, path, max(1, line - 20), line + 20)
        if "error" not in ex:
            items.append(
                _ev(
                    "code",
                    ex,
                    f"Source around the crashing line {path}:{line} (release v{issue.last_version})",
                )
            )
    return {"evidence": items}


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
    spec = LLMNodeSpec(
        node="classify_rca",
        system_prompt=_prompt("rca_system.md"),
        **deps.agent_type["nodes"]["classify_rca"],
    )
    prompt = (
        f"Issue {issue.id} from Vitals in repo {issue.repo} (component '{issue.component}', {issue.language}).\n"
        f"Title: {issue.title}\nEvents: {issue.events}; versions {issue.first_version}→{issue.last_version}.\n"
        "\n"
        f"Evidence bundle (pre-collected, pruned):\n{_bundle(state.evidence)}\n\n"
        f"Code paths are repo-relative; the client lives at the repo root. Investigate and submit the RCA."
    )
    r = await deps.runner().run(spec, prompt, RCAOutput, mcp_env=_code_repos_env(state))
    _stop_if_out_of_quota(r, state, "classify_rca")
    if r.output:
        rca.output = RCAOutput.model_validate(r.output)
    rca.llm = _llm_summary(r)
    if r.status != "ok" or rca.output is None:
        raise RuntimeError(f"RCA agent ended with status {r.status}: {r.error or 'no result'}")
    return {"rca": rca, "decisions": decisions, "costs": {**state.costs, "classify_rca": r.cost_usd}}


# ---- N4 mitigate ----------------------------------------------------------------------------


async def mitigate(state: RunState, deps: Deps) -> dict[str, Any]:
    from debugassist.mcp_servers import feature_flags as ff

    issue, rca = state.issue, state.rca
    assert issue and rca and rca.output
    corr_items = [e.data for e in state.evidence if e.kind == "flag_correlation"]
    flag = rca.output.implicated_flag or (corr_items[0]["flag"] if corr_items else None)
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
    if d11.action == "rollback_flag" and corr["significant"]:
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


async def fix(state: RunState, deps: Deps) -> dict[str, Any]:
    """Two enforced phases: (1) reproduce — tests only, must fail on the release; (2) fix — make it pass."""
    issue, rca = state.issue, state.rca
    assert issue and rca and rca.output
    sb = _sandbox(state)
    comp = _component_cfg(state, sb.worktree)
    attempt = len(state.fix_attempts) + 1
    base = f"v{issue.last_version}"
    # Every attempt (and a resumed run) starts from the release tag, not the branch head: after a PR
    # the bot branch holds the previous fix commit. Ignored dirs (node_modules…) survive.
    subprocess.run(["git", "reset", "-q", "--hard", base], cwd=sb.worktree, check=True)
    subprocess.run(["git", "clean", "-qfd"], cwd=sb.worktree, check=False)
    if attempt == 1:
        res = sb.install(str(comp["setup"]), workdir=issue.component)
        if res.exit_code:
            raise RuntimeError(f"dependency install failed: {res.output[-1500:]}")
    o = rca.output
    cfg = deps.agent_type["nodes"]["fix"]
    context = (
        f"Repository {issue.repo}, component dir '{issue.component}' ({issue.language}); commands run from there. Release {base}.\n"
        f"Component test command: `{comp['test']}`; tests live under `{comp.get('test_file_glob', 'test/')}`.\n"
        + (f"CI also runs `{comp['lint']}`; it must pass.\n" if comp.get("lint") else "")
        + "\n"
        f"Root cause: {o.root_cause}\nLocation: {o.location.file} → {o.location.function}"
        f"{f' (line {o.location.line})' if o.location.line else ''}\nReproduction idea: {o.reproduction}\n"
        f"Correct fix direction: {o.fix_direction}\n"
    )
    if state.validation and state.validation.attempts:
        context += f"\nThe previous attempt failed validation:\n{json.dumps(state.validation.attempts[-1], default=str)[:3000]}\nTry a different approach.\n"
    costs = dict(state.costs)
    fa = FixAttempt(n=attempt)

    # Phase 1: reproduce (only test files may be written)
    repro_cfg: dict[str, Any] = {**cfg, "max_turns": min(15, int(cfg["max_turns"]))}
    repro_spec = LLMNodeSpec(
        node=f"reproduce_{attempt}" if attempt > 1 else "reproduce",
        system_prompt=_prompt("reproduce_system.md"),
        **repro_cfg,
    )
    tools = build_workspace_tools(
        sb, allow_edits=True, allow_commands=True, editable=is_test_path, workdir=issue.component
    )
    feedback = ""

    def check_repro(out: dict[str, Any]) -> str | None:
        path = str(out.get("test_file", ""))
        if not is_test_path(path) or not (sb.worktree / path).is_file():
            return f"{path} does not exist as a test file. Create it with write_file first."
        cmd = _test_cmd(issue.language, path, issue.component)
        res = sb.run(cmd, workdir=issue.component)
        if res.exit_code == 0:
            return f"`{cmd}` passes on the current (buggy) code, so it does not reproduce the bug."
        if (
            "No test files found" in res.output
            or "SyntaxError" in res.output
            or "Cannot find module" in res.output
        ):
            return f"`{cmd}` failed for an unrelated reason:\n{res.output[-800:]}"
        if problem := _static_problem(sb, comp, issue.component):
            return (
                f"the test reproduces the bug, but {problem}\nClean up the test file (e.g. unused imports)."
            )
        return None

    for _ in range(2):
        r1 = await deps.runner(_apply_diff(sb)).run(
            repro_spec,
            context + feedback + "\nWrite and run the reproduction test, then submit.",
            ReproOutput,
            tools=tools,
            diff_fn=lambda: sb.diff(base),
            validate_output=check_repro,
        )
        _stop_if_out_of_quota(r1, state, "fix")
        costs[repro_spec.node] = costs.get(repro_spec.node, 0.0) + r1.cost_usd
        fa.llm["reproduce"] = _llm_summary(r1)
        _revert_non_tests(sb)  # source is read-only while reproducing, whatever the agent ran
        out = (
            r1.output if r1.output and (sb.worktree / str(r1.output.get("test_file", ""))).is_file() else None
        )
        if out is None:
            # The model sometimes stops without submitting: trust the worktree, not its word.
            written = _new_test_files(sb)
            if not written:
                feedback = "\nYou did not write a reproduction test. Create one with write_file, run it, then submit."
                continue
            out = {
                "test_file": written[-1],
                "asserts": "(inferred from the test file the agent wrote)",
                "failure": "(not reported by the agent; see the verification run)",
            }
            fa.llm["reproduce"]["note"] = "no valid submission; using the test file found in the worktree"
        fa.repro = ReproOutput.model_validate(out)
        cmd = _test_cmd(issue.language, fa.repro.test_file, issue.component)
        run = sb.run(cmd, workdir=issue.component)
        fa.repro_run = {"command": cmd, "exit_code": run.exit_code, "output_tail": run.output[-2500:]}
        fa.repro_verified = (
            run.exit_code != 0
            and is_test_path(fa.repro.test_file)
            and (sb.worktree / fa.repro.test_file).is_file()
        )
        if fa.repro_verified:
            break
        feedback = (
            f"\nYour test `{cmd}` exited {run.exit_code} on the buggy code, so it does not reproduce the bug "
            f"(output tail: {run.output[-800:]}). Write a test that fails for the reason in the root cause."
        )
    if not fa.repro_verified:
        fa.diff = sb.diff(base)
        fa.files = changed_files(fa.diff)
        return {"fix_attempts": [*state.fix_attempts, fa], "costs": costs}

    # Phase 2: fix (source files editable; the reproduction test is frozen)
    repro = fa.repro
    assert repro
    frozen = repro.test_file
    frozen_content = (sb.worktree / frozen).read_text()
    tools = build_workspace_tools(
        sb,
        allow_edits=True,
        allow_commands=True,
        editable=lambda p: p != frozen and not p.startswith(("src/vendor/", "vendor/")),
        workdir=issue.component,
    )
    fix_spec = LLMNodeSpec(
        node=f"fix_{attempt}" if attempt > 1 else "fix", system_prompt=_prompt("fix_system.md"), **cfg
    )
    prompt = (
        context
        + f"\nReproduction test: `{repro.test_file}` — run with `{fa.repro_run['command']}`; it currently fails:\n"
        f"{fa.repro_run['output_tail'][-1500:]}\n\nFix the bug so this test and the component suite pass, then submit."
    )

    def check_fix(out: dict[str, Any]) -> str | None:
        (sb.worktree / frozen).write_text(frozen_content)
        if not [f for f in changed_files(sb.diff(base)) if not is_test_path(f)]:
            return "you have not changed any source file yet"
        res = sb.run(str(fa.repro_run["command"]), workdir=issue.component)
        if res.exit_code != 0:
            return f"the reproduction test still fails:\n{res.output[-1200:]}"
        suite = sb.run(str(comp["test"]), workdir=issue.component)
        if suite.exit_code != 0:
            return f"the component suite fails:\n{suite.output[-1200:]}"
        return _static_problem(sb, comp, issue.component)

    r2 = await deps.runner(_apply_diff(sb)).run(
        fix_spec, prompt, FixOutput, tools=tools, diff_fn=lambda: sb.diff(base), validate_output=check_fix
    )
    _stop_if_out_of_quota(r2, state, "fix")
    costs[fix_spec.node] = costs.get(fix_spec.node, 0.0) + r2.cost_usd
    fa.llm["fix"] = _llm_summary(r2)
    (sb.worktree / frozen).write_text(frozen_content)  # the reproduction test is the contract: restore it
    fa.output = FixOutput.model_validate(r2.output) if r2.output else None
    fa.diff = sb.diff(base)
    fa.files = changed_files(fa.diff)
    return {"fix_attempts": [*state.fix_attempts, fa], "costs": costs}


# ---- N6 validate ----------------------------------------------------------------------------


async def validate(state: RunState, deps: Deps) -> dict[str, Any]:
    """Failing-before / passing-after proof on the reproduction test, plus the full component suite."""
    issue = state.issue
    assert issue and state.fix_attempts
    sb = _sandbox(state)
    comp = _component_cfg(state, sb.worktree)
    fa = state.fix_attempts[-1]
    v = state.validation or Validation()
    record: dict[str, Any] = {"attempt": fa.n, "tier": "unit"}
    src = [f for f in fa.files if not is_test_path(f)]
    if not fa.repro_verified or not fa.repro:
        record.update(result="no reproduction test that fails on the release", repro_run=fa.repro_run)
    elif not src:
        record.update(result="no source change")
    else:
        cmd = str(fa.repro_run["command"])
        after = sb.run(cmd, workdir=issue.component)
        v.passing_after = TestRun(
            label="reproduction test with the fix",
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
            before = sb.run(cmd, workdir=issue.component)
        finally:
            subprocess.run(["git", "apply", "-"], input=src_diff, text=True, cwd=sb.worktree, check=True)
        v.failing_before = TestRun(
            label="reproduction test on the release (expected to fail)",
            command=cmd,
            exit_code=before.exit_code,
            output_tail=before.output[-3000:],
        )
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
        and (v.static is None or v.static.exit_code == 0)
    )
    v.attempts.append(record)
    return {"validation": v}


async def decide_retry(state: RunState, deps: Deps) -> bool:
    """D15 inside the fixed attempt cap."""
    v = state.validation
    cap = int(deps.agent_type.get("validation", {}).get("max_attempts", 3))
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


def _pr_body(state: RunState) -> str:
    issue, tr, rca, m, v = state.issue, state.triage, state.rca, state.mitigation, state.validation
    assert issue and rca and rca.output
    o = rca.output
    fa = state.fix_attempts[-1]
    lines = [
        "## Summary",
        o.summary,
        "",
        f"Fixes the crash reported by Vitals [{issue.id}]({issue.url}) — `{issue.title}` ({issue.events} events, {issue.app} {issue.first_version}→{issue.last_version})."
        + (
            f" Jira: [{tr.jira_key}]({tr.jira_url})."
            if tr and tr.jira_key and tr.jira_url and tr.jira_url.startswith("http")
            else ""
        ),
        "",
        "## Root cause",
        o.root_cause,
        "",
        f"**Location:** `{o.location.file}` → `{o.location.function}`"
        + (f" (line {o.location.line})" if o.location.line else ""),
    ]
    if o.suspect_commit:
        lines.append(f"**Introduced by:** {o.suspect_commit}")
    if o.implicated_flag:
        lines.append(f"**Behind flag:** `{o.implicated_flag}`")
    lines += ["", "## Evidence", "| Claim | Evidence |", "|---|---|"]
    lines += [
        f"| {c.text.replace('|', '/')} | {', '.join(f'`{e}`' for e in c.evidence_ids) or '—'} |"
        for c in o.claims
    ]
    lines += ["", "<details><summary>Timeline</summary>", ""]
    lines += [f"- **{t.when}** — {t.event} {' '.join(f'`{e}`' for e in t.evidence_ids)}" for t in o.timeline]
    lines += ["", "</details>", ""]
    if m and m.flag:
        lines += [
            "## Mitigation",
            f"{m.detail}. Exposed sessions: {m.correlation.get('exposed')}; unexposed: {m.correlation.get('unexposed')}; "
            f"z={m.correlation.get('z')}, p={m.correlation.get('p_value'):.2g}.",
            "",
        ]
    if fa.output:
        lines += [
            "## Fix",
            fa.output.summary,
            "",
            f"*Why:* {fa.output.rationale}",
            f"*Strategy:* {fa.output.strategy} · *Risk:* {fa.output.risk}",
            "",
        ]
    lines += ["## Validation"]
    if v:
        if v.failing_before:
            lines += [
                f"- ❌ before the fix: `{v.failing_before.command}` → exit {v.failing_before.exit_code} (reproduces the bug)"
            ]
        if v.passing_after:
            lines += [f"- ✅ with the fix: `{v.passing_after.command}` → exit {v.passing_after.exit_code}"]
        if v.suite:
            lines += [
                f"- {'✅' if v.suite.exit_code == 0 else '❌'} full suite: `{v.suite.command}` → exit {v.suite.exit_code}"
            ]
        if v.static:
            lines += [
                f"- {'✅' if v.static.exit_code == 0 else '❌'} CI checks: `{v.static.command}` → exit {v.static.exit_code}"
            ]
        if v.failing_before:
            lines += [
                "",
                "<details><summary>Failing-before output</summary>",
                "",
                "```",
                v.failing_before.output_tail[-1500:],
                "```",
                "</details>",
            ]
    lines += [
        "",
        "## Risk & rollback",
        f"Risk: {fa.output.risk if fa.output else 'unknown'}. Rollback: revert this PR"
        + (f"; the flag `{m.flag}` can stay off until it ships" if m and m.flag else "")
        + ".",
        "",
    ]
    rca_llm = rca.llm
    cost = sum(state.costs.values())
    lines += [
        "---",
        f"Opened by **DebugAssist** (automated) · run `{state.run_id}` · reasoning: {rca_llm.get('model')} "
        f"({rca_llm.get('mode')}) · decisions: Clef · RCA {rca_llm.get('turns')} turns · total LLM cost ${cost:.4f}. "
        "Review before merging.",
    ]
    return "\n".join(lines)


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
                issue.gh_repo, branch, base, title, _pr_body(state), draft=ship.outcome == "draft_pr"
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
    if tr:
        text = (
            f"{issue.id} {issue.title[:80]} — {'PR ' + pr_info.url if pr_info else ship.outcome}. "
            f"Root cause: {rca.output.summary[:200] if rca.output else 'n/a'}"
        )
        notes.append(
            {
                "kind": "slack",
                "to": tr.oncall,
                **deps.slack.message(
                    f"@{tr.oncall}",
                    text,
                    {"jira": tr.jira_url or "", "vitals": issue.url, "pr": pr_info.url if pr_info else ""},
                ),
            }
        )
    return {**out, "notifications": notes}


async def post_merge_watch(state: RunState, deps: Deps) -> dict[str, Any]:
    """Placeholder (P8): after merge + deploy, watch crash rates (D17) and restore the flag."""
    return {
        "status": "done",
        "notifications": [
            *state.notifications,
            {"kind": "watch", "detail": "post-merge watch arrives in P8"},
        ],
    }
