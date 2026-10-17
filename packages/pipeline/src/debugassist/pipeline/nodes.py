"""Pipeline nodes N0–N9 (minimal-but-real versions for the walking skeleton).

Deterministic nodes call backends directly (the same functions the MCP servers expose, so evidence
ids match what agents see); LLM nodes go through the LLMRunner seam; decisions go through Clef;
every write goes through the policy gate.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx
import yaml
from langchain_core.tools import BaseTool, tool

from debugassist.core import hostgit, untrusted
from debugassist.core.ablation import ablated, bisect_enabled, call_variants, second_repro, second_repro_mode
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
from debugassist.pipeline import (
    app_intake,
    bisect,
    budget,
    callvariants,
    collector,
    crossrepo,
    e2e,
    fixplan,
    postmerge,
    pr_body,
    profile,
    release,
    skills,
    usages,
)
from debugassist.pipeline import rca as rca_mod
from debugassist.pipeline.deps import APPS, Deps
from debugassist.pipeline.notify import notify
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


def run_values(state: RunState) -> dict[str, str]:
    """The run's values for in-process code tools (`core.runctx`), set around every node by the graph."""
    values = {"DEBUGASSIST_RUN_ID": state.run_id, "DEBUGASSIST_MODE": state.mode}
    if state.issue:
        sb = _sandbox(state)
        values["CODE_REPOS"] = json.dumps(crossrepo.code_repos(state.run_id, state.issue, sb.worktree))
    return values


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
        "DA_CONTEXT",
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


def _pipeline_yaml(worktree: Path, issue: Issue | None = None) -> dict[str, Any]:
    """How to build and test the repository, as of the release under test — never the agent's copy.

    The fix agent may edit any file in its worktree, `.DebugAssist/pipeline.yaml` included; read from there, a
    `test: "true"` would make "the suite passes" mean nothing (audit P2-8)."""
    if issue is not None:
        shown = hostgit.run(worktree, "show", f"v{issue.last_version}:.DebugAssist/pipeline.yaml")
        if shown.returncode == 0:
            return yaml.safe_load(shown.stdout)
        if hostgit.run(worktree, "rev-parse", "--verify", "-q", f"v{issue.last_version}").returncode == 0:
            raise RuntimeError(f"v{issue.last_version} has no .DebugAssist/pipeline.yaml")
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


# How test runners report a failed assertion: pytest / unittest, vitest / jest / chai, node:assert, Go's testing.
ASSERTION_FAILED = re.compile(
    r"AssertionError|^E\s+assert\b|\bassert .* (==|!=|is|in) |Expected:|Received:|expected .+ to |"
    r"AssertionError \[ERR_ASSERTION\]|^\s+\S+_test\.go:\d+: |--- FAIL: ",
    re.M,
)
TIMEOUT_MARKERS = ("Test timed out", "Exceeded timeout of", "Timeout of", "Failed: Timeout >")


def _error_signature(issue: Issue) -> str | None:
    """The production error message a reproduction must show (crashes only), e.g.
    "Cannot read properties of undefined (reading 'riderId')" from "TypeError: Cannot read …"."""
    if issue.kind != "crash":
        return None
    msg = re.sub(r"^[A-Za-z_.]*(Error|Exception)\b:?\s*", "", issue.title).strip()
    return msg or None


REPORTED_ERROR = re.compile(r"\w*(Error|Exception)\b|Traceback|panic:|crash|throws?\b|raised?\b", re.I)


def _wrong_value_report(issue: Issue) -> bool:
    """A report of a wrong result rather than an error: not a crash, and neither its title nor its text names an
    exception (a GitHub issue that pastes a traceback is a crash report whatever its kind)."""
    if issue.kind == "crash":
        return False
    report = issue.report or {}
    text = " ".join([issue.title, *(str(v) for v in report.values() if isinstance(v, str))])
    return not REPORTED_ERROR.search(text)


def _error_type(issue: Issue) -> str | None:
    """The reported exception's class name ("TypeError", "KeyError"), last component only."""
    m = re.match(r"^([A-Za-z_][\w.]*(?:Error|Exception))\b", issue.title)
    return m.group(1).split(".")[-1] if m and issue.kind == "crash" else None


def error_pattern(issue: Issue) -> re.Pattern[str] | None:
    """What the reproduction's output must contain to show the reported error (ROADMAP-100 011).

    Not the message as a substring: numbers and addresses vary between runs (`index 7`, `0x7f3a…`), whitespace
    between runtimes, and a test that only *asserts* the message text ("expected … to throw 'Cannot read …'")
    contains it without raising it. So: the exception type immediately before the message, as a runtime prints a
    raised error, with numbers and hex addresses free and runs of whitespace equal."""
    sig = _error_signature(issue)
    if not sig:
        return None
    parts = re.split(r"(0x[0-9a-fA-F]+|\d+(?:\.\d+)?)", sig)
    body = "".join(
        r"\S+" if i % 2 else re.sub(r"(\\\s)+", r"\\s+", re.escape(p)) for i, p in enumerate(parts)
    )
    kind = _error_type(issue)
    return re.compile((rf"(?<!\w){re.escape(kind)}:\s*" if kind else "") + body)


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
    if _wrong_value_report(issue) and not ASSERTION_FAILED.search(output):
        # A wrong value, not a crash (ROADMAP-100 012): the test must fail on an assertion about the value, not on an
        # error of its own (a NameError, a bad import, a typo) that would fail with or without the bug.
        return (
            f"`{cmd}` fails, but not on an assertion: the report is a wrong result, so the test must assert the "
            f"correct value and fail on that assertion.\n{output[-600:]}"
        )
    pattern = error_pattern(issue)
    if pattern is not None and not pattern.search(output):
        kind, sig = _error_type(issue), _error_signature(issue)
        shown = f"{kind}: {sig}" if kind else sig
        return (
            f"`{cmd}` fails, but not with the reported error `{shown}` raised by the code under test (a test "
            f"that only asserts the message does not count); reproduce that failure.\n{output[-600:]}"
        )
    return None


repro_problem = _repro_problem  # for the evaluation's replays (eval replay-bisect)


def _run_on_release(sb: Sandbox, base: str, run: Callable[[Sandbox], CommandResult]) -> CommandResult | None:
    """Run in a disposable checkout of the release with the worktree's tests but not its source change (P3-16:
    the worktree, and the fix in it, is never touched). Against the release, not HEAD: once a fix is committed
    (diff fixer, a resumed run), HEAD already contains it. None if there is no source change."""
    changed = release.changes(sb.worktree, base)
    if all(is_test_path(p) for p in changed):
        return None
    with release.release_checkout(sb, base, [p for p in changed if is_test_path(p)]) as rsb:
        return run(rsb)


def _component_cfg(state: RunState, worktree: Path) -> dict[str, Any]:
    assert state.issue
    cfg = _pipeline_yaml(worktree, state.issue)["components"]
    if state.issue.component == ".":
        return next(iter(cfg.values()))
    return cfg[state.issue.component]


# ---- N0 ingest ------------------------------------------------------------------------------


async def ingest(state: RunState, deps: Deps) -> dict[str, Any]:
    ref = state.issue_ref
    if ref.upper().startswith("BD-"):
        return _with_agent_type(await collector.ingest_bugdrop(ref, deps), deps)
    if ref.upper().startswith("GH-"):
        return _with_agent_type(collector.ingest_github(ref), deps)
    if ref.upper().startswith("GHA:"):
        if deps.app is None:
            raise ValueError("a GitHub App issue needs the app configured (docs/github-app.md)")
        return _with_agent_type(app_intake.ingest(ref, deps.app), deps)
    if not ref.upper().startswith("VIT-"):
        raise ValueError(
            f"unknown issue reference {ref!r}: expected a Vitals issue (VIT-…), a BugDrop report (BD-…) "
            "a frozen GitHub issue (GH-…) or a GitHub App issue (GHA:owner/repo#123)"
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
    return {"bugdrop": "BugDrop report", "github": "GitHub issue"}.get(issue.source, "Vitals issue")


_notify = notify  # the name nodes have always used


def app_comment(state: RunState, pr_url: str | None, outcome: str) -> str:
    """What the run says on the GitHub issue it was asked about (starts with the app's marker)."""
    issue, rca = state.issue, state.rca
    assert issue
    o = rca.output if rca else None
    lines = [f"<!-- debugassist:run {state.run_id} -->", "**DebugAssist** looked into this issue."]
    if o:
        lines += ["", o.summary, "", f"**Where:** `{o.location.file}` → `{o.location.function}`"]
        b = state.bisect or {}
        if b.get("result") == "found":
            lines.append(
                f"**Introduced by:** `{b['first_bad']}` {b.get('subject', '')} (bisected with the test)"
            )
        elif o.suspect_commit:
            lines.append(f"**Suspected cause:** `{o.suspect_commit}`")
    if pr_url:
        lines += ["", f"A fix with a reproduction test is ready for review: {pr_url}"]
    else:
        lines += [
            "",
            {
                "rca_only": "No fix proposed: the root cause is outside this repository's code.",
                "escalate": "No fix proposed: this needs a maintainer's decision.",
            }.get(outcome, f"No pull request ({outcome.replace('_', ' ')})."),
        ]
    lines += [
        "",
        f"<sub>Automated analysis, run `{state.run_id}`. Remove the label to stop; remove and re-add it to rerun.</sub>",
    ]
    return "\n".join(lines)


def _comment_app_issue(
    deps: Deps, state: RunState, pr_info: PRInfo | None, outcome: str
) -> list[dict[str, Any]]:
    """GitHub App issues: the outcome as a comment on the issue, through the policy gate."""
    issue = state.issue
    if issue is None or issue.app_issue is None or deps.app is None:
        return []
    verdict = deps.gate.verdict("github.comment", repo=issue.gh_repo)
    result: Any = "dry_run"
    marker = f"<!-- debugassist:run {state.run_id} -->"
    if verdict is Verdict.LIVE:
        try:
            if any(c.lstrip().startswith(marker) for c in deps.app.comments(issue.gh_repo, issue.app_issue)):
                result = "already commented"  # a resumed run: this run's comment is there (ROADMAP-100 019)
            else:
                deps.app.comment(
                    issue.gh_repo,
                    issue.app_issue,
                    app_comment(state, pr_info.url if pr_info else None, outcome),
                )
                result = "commented"
        except (httpx.HTTPError, PermissionError, KeyError) as exc:
            result = f"failed: {type(exc).__name__}"
    deps.gate.record(
        "github.comment",
        verdict,
        run_id=state.run_id,
        detail={"repo": issue.gh_repo, "issue": issue.app_issue},
        result=result,
    )
    return [{"kind": "comment", "issue": f"{issue.gh_repo}#{issue.app_issue}", "result": result}]


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


def _repo_owner(issue: Issue) -> tuple[str, str]:
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
        comps: Any = _pipeline_yaml(ROOT / "targets" / issue.repo, issue).get("components") or {}
        comp: Any = comps.get(issue.component) or next(iter(comps.values()), None)
        declared = comp.get("owner") if comp else None
    except (OSError, RuntimeError, StopIteration, AttributeError):
        declared = None
    return (str(declared), "pipeline.yaml") if declared else ("maintainers", "default")


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
    real_repo = issue.source == "github"
    if real_repo and owner_team is None:
        # A real repository has its own maintainers, not a MiniRide team (ROADMAP-100 077): its CODEOWNERS
        # default rule, else the owner its pipeline.yaml names, else "maintainers".
        owner_team, owner_source = _repo_owner(issue)
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
        oncall=team if real_repo else _oncall(deps.catalog, team),
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
            f"Opened automatically from {_source_label(issue)} {issue.id} "
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
        ("para", f"{_source_label(issue)}: {issue.url}"),
        ("para", f"DebugAssist run {state.run_id} is investigating."),
    ]
    verdict = deps.gate.verdict("jira.create_issue")
    label = _jira_label(issue.id)
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
    spec = LLMNodeSpec(
        node="classify_rca",
        system_prompt=profile.for_issue(_prompt("rca_system.md"), issue) + skill_prompt,
        **cfg,
    )
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
        f"Issue {issue.id} from {_source_label(issue).split()[0]}, seen in repo "
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
    if not flag:
        return {"mitigation": Mitigation(detail="no feature flag implicated; nothing to roll back")}
    current = ff.get_flag(flag)
    cs = CompactState().add("flag", {"name": flag, "rollout_pct": current["rollout_pct"]}, priority=0)
    if issue.fingerprint:
        # A crash group: compare the crash rate of sessions exposed to the flag with the rest.
        corr = ff.flag_crash_correlation(issue.fingerprint, flag)
        signal = {
            k: corr[k]
            for k in ("exposed", "unexposed", "z", "p_value", "significant", "share_of_affected_exposed")
        }
        supported = bool(corr["significant"])
        cs.add("crash_rates", {k: v for k, v in signal.items() if k != "significant"}, priority=0)
    elif rca.output.category == "flag_config":
        # A rider report has no crash group to split by exposure, but the RCA found the flag's configuration to
        # be the defect itself. D11 weighs that against the flag's rollout and its recent changes.
        events = ff.rollout_history(flag, limit=5)["events"]
        signal = {"source": "rca: flag configuration is the defect", "recent_changes": events}
        supported = bool(events) and bool(current["rollout_pct"])
        cs.add("recent_changes", events, priority=0)
    else:
        return {
            "mitigation": Mitigation(
                flag=flag,
                detail=f"{flag}: no crash group to compare exposure against; rollback not considered",
            )
        }
    cs.add(
        "rca",
        {"category": rca.output.category, "summary": rca.output.summary, "root_cause": rca.output.root_cause},
        priority=1,
    )
    d11 = await deps.engine.decide("D11", cs, ctx=RunContext(run_id=state.run_id, issue_id=issue.id))
    m = Mitigation(
        flag=flag,
        correlation=signal,
        decision={"p": d11.p, "band": d11.band, "action": d11.action},
    )
    if d11.action == "rollback_flag" and supported and not current["rollout_pct"]:
        m.detail = f"{flag}: rollback warranted, but the flag is already at 0% — nothing to roll back"
    elif d11.action == "rollback_flag" and supported:
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
        res = ff.apply_rollout(
            flag,
            0,
            reason=f"{issue.id}: {rca.output.summary[:200]}",
            authorized=verdict is Verdict.LIVE,
            gate=deps.gate,
            run_id=state.run_id,
        )
        m.action = "rolled_back" if res["applied"] else "dry_run"
        m.rolled_back_from = int(res["from_percent"])
        m.detail = f"{flag}: {res['from_percent']}% → 0% ({'applied' if res['applied'] else 'dry run — policy requires approval'})"
    else:
        m.detail = f"{flag}: no rollback (Clef band {d11.band}, evidence supports it: {supported})"
    return {"mitigation": m, "decisions": [*state.decisions, d11.ledger_id or ""]}


# ---- N5 fix ---------------------------------------------------------------------------------


def _apply_diff(sb: Sandbox) -> Any:
    def apply(diff: str) -> None:
        hostgit.run(sb.worktree, "apply", "--whitespace=nowarn", "-", input=diff, check=True)

    return apply


def _status(sb: Sandbox) -> list[str]:
    """Paths `git status` reports, both sides of a rename included; NUL-separated, so quoted, escaped and
    renamed paths (`old -> new`) are not misread (audit P3-22)."""
    raw = hostgit.run(
        sb.worktree, "status", "--porcelain=v1", "-z", "--untracked-files=all", check=True
    ).stdout
    parts, out, i = raw.split("\0"), list[str](), 0
    while i < len(parts):
        entry, i = parts[i], i + 1
        if not entry:
            continue
        out.append(entry[3:])
        if "R" in entry[:2] or "C" in entry[:2]:  # the source path follows as its own field
            out.append(parts[i])
            i += 1
    return out


def _revert_non_tests(sb: Sandbox) -> None:
    for path in _status(sb):
        if is_test_path(path):
            continue
        if hostgit.run(sb.worktree, "cat-file", "-e", f"HEAD:{path}").returncode == 0:
            hostgit.run(sb.worktree, "checkout", "-q", "HEAD", "--", path, check=False)
        else:  # new in the worktree: drop it from the index (intent-to-add) and from disk
            hostgit.run(sb.worktree, "rm", "-q", "--cached", "--ignore-unmatch", "--", path, check=False)
            (sb.worktree / path).unlink(missing_ok=True)


def _new_test_files(sb: Sandbox) -> list[str]:
    tests = [f for f in _status(sb) if is_test_path(f) and (sb.worktree / f).is_file()]
    return sorted(set(tests), key=lambda f: (sb.worktree / f).stat().st_mtime)


def _test_cmd(language: str, test_file: str, component: str, template: str | None = None) -> str:
    """The pipeline, not the agent, decides how the reproduction test is run: the repo's own `test_one` command
    from its .DebugAssist/pipeline.yaml when it declares one, else the language's default runner."""
    rel = test_file if component == "." else test_file.removeprefix(f"{component}/")
    if template:
        return template.format(file=rel)
    if language == "python":
        return f"uv run --offline pytest -q {rel}"
    if language == "go":
        pkg = "./" + rel.rsplit("/", 1)[0] if "/" in rel else "."
        return f"go test {pkg}"
    return f"pnpm exec vitest run {rel}"


def _run_test(sb: Sandbox, issue: Issue, cmd: str) -> CommandResult:
    """Unit/integration tests run in the sandbox; E2E specs run against a build of the worktree."""
    if e2e.is_e2e_cmd(cmd):
        return e2e.run(sb, _pipeline_yaml(sb.worktree, issue), issue.component, cmd)
    return sb.run(cmd, workdir=issue.component)


def _repro_cmd(issue: Issue, test_file: str) -> str:
    rel = test_file if issue.component == "." else test_file.removeprefix(f"{issue.component}/")
    if rel.startswith("e2e/"):
        return e2e.e2e_cmd(test_file, issue.component)
    # The same source as `test`, `lint` and `setup` (ROADMAP-100 014): the release's own config, read through the
    # target's main checkout (no agent writes there), not that checkout's working copy, which may have moved on.
    try:
        cfg: dict[str, Any] = _pipeline_yaml(ROOT / "targets" / issue.repo, issue) or {}
    except (OSError, RuntimeError):  # no checkout or no config: the language's default runner
        cfg = {}
    comps = cast(dict[str, dict[str, Any]], cfg.get("components") or {})
    template = cast(str | None, (comps.get(issue.component) or {}).get("test_one"))
    return _test_cmd(issue.language, test_file, issue.component, template)


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
            sb, _pipeline_yaml(sb.worktree, issue), issue.component, e2e.e2e_cmd(test_file, issue.component)
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
    before = _run_on_release(sb, base, lambda rsb: _run_test(rsb, issue, cmd))
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
    hostgit.run(sb.worktree, "reset", "-q", "--hard", base, check=True)
    hostgit.run(sb.worktree, "clean", "-qfd", check=False)


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
        plan, ledgers = await fixplan.plan(sb, state, deps, _pipeline_yaml(sb.worktree, issue))
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


def _at(sb: Sandbox, base: str, path: str) -> str | None:
    """The file as it is in the release, None if it is not there. (Not `git ls-files`: the runner's diff marks new
    files intent-to-add, which lists them as tracked.)"""
    out = hostgit.run(sb.worktree, "show", f"{base}:{path}")
    return out.stdout if out.returncode == 0 else None


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
            system_prompt=_prompt("reproduce_check_system.md") + skill_prompt,
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
            if p in taken or _at(rsb, base, p) is not None:
                return f"{p} is already taken; write your test in a new file with another name."
            cmd = _repro_cmd(issue, p)
            res = _run_test(rsb, issue, cmd)
            return _repro_problem(cmd, res.exit_code, res.output, issue)

        uses = ""
        if second_repro_mode() == "callers":
            names = usages.names_for(
                rsb.worktree, rca.output.location.function, usages.report_text(issue.report)
            )
            uses = usages.collect(rsb.worktree, names, exclude={rca.output.location.file})
            rec["usages"] = {"names": names, "chars": len(uses)}
        r = await deps.runner(_apply_diff(rsb)).run(
            spec,
            check_prompt(issue, comp, base, loc, uses),
            ReproOutput,
            tools=tools,
            diff_fn=lambda: rsb.diff(base),
            validate_output=check,
        )
        _stop_if_out_of_quota(r, state, "validate")
        cost = r.cost_usd
        rec["llm"] = _llm_summary(r)
        _revert_non_tests(rsb)  # source is read-only for the checker, whatever it ran
        written = [
            f
            for f in _new_test_files(rsb)
            if f not in taken and _at(rsb, base, f) is None and not (rsb.worktree / f).is_symlink()
        ]
        claimed = str((r.output or {}).get("test_file", ""))
        path = claimed if claimed in written else (written[-1] if written else None)
        if path is None:
            rec["result"] = "no second reproduction written; not checked"
            return None, rec, cost
        cmd = _repro_cmd(issue, path)
        before = _run_test(rsb, issue, cmd)
        rec.update(test_file=path, command=cmd, before_exit=before.exit_code)
        if problem := _repro_problem(cmd, before.exit_code, before.output, issue):
            rec["result"] = (
                f"the second test does not reproduce the bug on the release; not checked: {problem[:300]}"
            )
            return None, rec, cost
        rec["test_source"] = (rsb.worktree / path).read_text()[:2500]
        second = release.patch(rsb.worktree, base, [path])
    # The fix's source change (not its tests) against the second test; a check, never part of the fix.
    with release.release_checkout(sb, base, classes.get("source", []), extra=second) as fsb:
        after = _run_test(fsb, issue, cmd)
    rec.update(after_exit=after.exit_code, after_tail=after.output[-1500:] if after.exit_code else "")
    rec["result"] = "passes with the fix" if after.exit_code == 0 else "fails with the fix"
    run = TestRun(
        label="second reproduction, written without seeing the fix, with the fix",
        command=cmd,
        exit_code=after.exit_code,
        output_tail=after.output[-3000:],
    )
    return run, rec, cost


def _python(comp: dict[str, Any]) -> str:
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
    py = _python(comp)
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
        res = _run_test(sb, issue, command)
        return res.exit_code, res.output

    def unrelated(code: int, output: str) -> bool:  # failed, but not as a reproduction (syntax, time-out, …)
        return code != 0 and _repro_problem(cmd, code, output, issue) is not None

    try:
        rel = test_file if issue.component == "." else test_file.removeprefix(f"{issue.component}/")
        found = bisect.prove_by_case(
            sb.worktree,
            f"v{issue.last_version}",
            test_file,
            cmd,
            bisect.pytest_case_command(cmd, rel),
            unrelated,
            run,
        )
    except (subprocess.CalledProcessError, OSError) as e:
        return {"result": "error", "why": str(e)[:300]}
    suspect = state.rca.output.suspect_commit if state.rca and state.rca.output else None
    return {**found, "rca_suspect": suspect, "agrees_with_rca": bisect.agrees(found, suspect)}


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
    base = f"v{issue.last_version}"
    # What this proof ran and with which config (ROADMAP-100 015): a reviewer, or a later run, can tell whether
    # two validations are comparable without re-reading the harness.
    record["harness"] = {
        "config_sha256": hashlib.sha256(
            json.dumps(_pipeline_yaml(sb.worktree, issue), sort_keys=True, default=str).encode()
        ).hexdigest()[:16],
        "from": base,
        "commands": {k: str(comp[k]) for k in ("setup", "test", "lint") if comp.get(k)}
        | ({"reproduction": str(fa.repro_run["command"])} if (fa.repro_run or {}).get("command") else {}),
    }
    src = [f for f in fa.files if not is_test_path(f)]
    if not fa.repro_verified or not fa.repro:
        record.update(result="no reproduction test that fails on the release", repro_run=fa.repro_run)
    elif not src:
        record.update(result="no source change")
    else:
        cmd = str(fa.repro_run["command"])
        # Against the release tag in disposable checkouts (P3-16): the worktree keeps the fix whatever happens
        # here, and a validate resumed after the fix was committed proves the same thing.
        classes = release.classify_changes(sb.worktree, base)
        v.changes, v.protected = classes, release.flagged(sb.worktree, base, classes)
        record.update(changes=classes, **({"protected": v.protected} if v.protected else {}))
        # Failing-before: the release with the reproduction test as written.
        with release.release_checkout(sb, base, [fa.repro.test_file]) as rsb:
            before = _run_test(rsb, issue, cmd)
        # Passing-after and the suite: the source change and the new tests only; pre-existing tests, the
        # harness and test-runner config, CI and lockfiles as in the release (P2-8), so a test edited to pass
        # or a skipped suite proves nothing. The reproduction test is part of the proof wherever it lives.
        proof = sorted({*release.proof_paths(classes), fa.repro.test_file})
        with release.release_checkout(sb, base, proof) as psb:
            after = _run_test(psb, issue, cmd)
            suite = psb.run(str(comp["test"]), workdir=issue.component)
        v.passing_after = TestRun(
            label=f"reproduction test ({fa.tier}) with the fix",
            command=cmd,
            exit_code=after.exit_code,
            output_tail=after.output[-3000:],
        )
        v.failing_before = TestRun(
            label=f"reproduction test ({fa.tier}) on the release (expected to fail)",
            command=cmd,
            exit_code=before.exit_code,
            output_tail=before.output[-3000:],
        )
        if before_problem := _repro_problem(cmd, before.exit_code, before.output, issue):
            record.update(failing_before_problem=before_problem[:600])
        v.suite = TestRun(
            label="full component suite with the fix (pre-existing tests as in the release)",
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
    costs = dict(state.costs)
    v.independent = None
    if v.passed and second_repro() and fa.tier != "e2e_env":
        run, rec, cost = await second_reproduction(state, deps, sb, comp, base)
        node = "reproduce_check" + (f"_{fa.n}" if fa.n > 1 else "")
        costs[node] = costs.get(node, 0.0) + cost
        record["second_reproduction"] = rec
        v.independent = run
        v.passed = run is None or run.exit_code == 0  # no valid second test: the fix is not held to one
    if v.passed and call_variants():
        record["call_variants"] = call_variants_check(sb, issue, comp)
        v.passed = record["call_variants"]["result"] != "fail"
    v.attempts.append(record)
    out: dict[str, Any] = {"validation": v, "costs": costs}
    if v.passed and bisect_enabled() and fa.tier != "e2e_env" and fa.repro:
        out["bisect"] = prove_culprit(state, sb, issue, fa.repro.test_file, str(fa.repro_run["command"]))
    return out


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
        cat = rca.output.category if rca and rca.output else None
        m = state.mitigation
        if cat == "flag_config" and m and m.action != "none":
            reason = f"the flag's configuration is the defect: {m.detail}"
        elif cat in ("infra", "device_os", "not_a_bug", "third_party_lib"):
            reason = f"not a code change in our repos ({cat}): reported and routed"
        else:
            reason = "not actionable or no fix"
        return {"ship": Ship(outcome="rca_only", decision={"reason": reason})}
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
    scope_note = ""
    has_fix = fa.repro_verified and any(not is_test_path(f) for f in fa.files)
    if not has_fix:
        outcome = "rca_only"  # no verified reproduction or no source change: nothing to put in a PR
    elif not (v and v.passed) and outcome == "open_pr":
        outcome = "draft_pr"  # never a ready PR without validation proof
    elif outcome == "open_pr" and v and v.protected:
        outcome = "draft_pr"  # a pre-existing test, harness, CI or lockfile changed: a flagged draft (P2-8)
    elif outcome == "open_pr" and (outside := _outside_plan(state)):
        outcome = (
            "draft_pr"  # the fix spread well past where the plan and the RCA put the defect (ROADMAP-100 017)
        )
        scope_note = (
            f"{len(outside)} changed source file(s) outside the planned location: {', '.join(outside[:5])}"
        )
    elif outcome == "open_pr" and not _ready_pr_allowed(state, deps):
        outcome = "draft_pr"  # a repository the app is installed on, not ours: draft PRs only (ADR 0008)
    return {
        "ship": Ship(
            outcome=outcome,
            risk=float(d16.chosen.get("risk", 0)),
            decision={
                "p": d16.p,
                "band": d16.band,
                "chosen": d16.chosen,
                **({"scope": scope_note} if scope_note else {}),
            },
        ),  # pyright: ignore[reportArgumentType]
        "decisions": [*state.decisions, d16.ledger_id or ""],
    }


SCOPE_SLACK = 2  # changed source files allowed beyond the planned ones (a helper, a sibling module)


def _outside_plan(state: RunState) -> list[str]:
    """Changed source files beyond the fix plan's focus and the RCA's location, when more than SCOPE_SLACK."""
    fa, rca, plan = state.fix_attempts[-1], state.rca, state.fix_plan
    planned = {f.split("::")[0].removeprefix("./") for f in (plan.focus if plan else [])}
    if rca and rca.output:
        planned.add(rca.output.location.file.removeprefix("./"))
    if not planned:
        return []
    outside = sorted(f for f in fa.files if not is_test_path(f) and f.removeprefix("./") not in planned)
    return outside if len(outside) > SCOPE_SLACK else []


def _commit_trailer(issue: Issue) -> str:
    """Where the fix came from: a Vitals crash, a BugDrop report, or the GitHub issue (audit P3-19)."""
    if issue.app_issue is not None or issue.source == "github":
        return f"Fixes: {issue.url}"
    return f"{'BugDrop' if issue.source == 'bugdrop' else 'Vitals'}: {issue.id}"


def _ready_pr_allowed(state: RunState, deps: Deps) -> bool:
    issue = state.issue
    return bool(issue and issue.app_issue is None and deps.gate.ready_pr_allowed(issue.gh_repo))


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
        # What is shipped, classified again (a resumed run may carry an older validation): a protected change
        # makes the PR a draft with a warning, whatever the ship decision said.
        shipped = f"v{issue.last_version}"
        flagged = release.flagged(sb.worktree, shipped, release.classify_changes(sb.worktree, shipped))
        v = state.validation
        if v is not None and flagged != v.protected:
            v = v.model_copy(update={"protected": flagged})
            state = state.model_copy(update={"validation": v})
            out["validation"] = v
        loc = rca.output.location if rca.output else None
        scope = (loc.file.split("/")[-2] if loc and "/" in loc.file else issue.component.strip("./")) or "app"
        title = (
            fa.output.commit_title
            if fa.output and fa.output.commit_title.startswith(("fix", "perf", "refactor"))
            else f"fix({scope}): {issue.title[:70]}"
        )[:100]
        # A run resumed after this step committed has nothing left to commit: push what is there (ROADMAP-100 019).
        if hostgit.run(sb.worktree, "status", "--porcelain", check=True).stdout.strip():
            sb.commit(
                f"{title}\n\n{rca.output.root_cause if rca.output else ''}\n\n{_commit_trailer(issue)}"
                + (f"\nJira: {tr.jira_key}" if tr and tr.jira_key else "")
            )
        branch = hostgit.run(sb.worktree, "branch", "--show-current", check=True).stdout.strip()
        base = issue.base_branch or f"release/{issue.last_version}"
        push_v = deps.gate.verdict("github.push_branch", repo=issue.gh_repo, branch=branch)
        pr_v = deps.gate.verdict("github.open_pr", repo=issue.gh_repo)
        if push_v is Verdict.LIVE and pr_v is Verdict.LIVE:
            if not deps.github.remote_branch_exists(issue.gh_repo, base):
                raise RuntimeError(
                    f"base branch {base} is not on GitHub; push it first (debugassist scenario inject --push)"
                )
            deps.github.push(sb.worktree, branch)
            # Enforced here too, not only in the ship gate: a resumed run may carry an older ship decision.
            draft = ship.outcome == "draft_pr" or not _ready_pr_allowed(state, deps) or bool(flagged)
            pr = deps.github.open_pr(issue.gh_repo, branch, base, title, pr_body.pr_body(state), draft=draft)
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
        key, gate = tr.jira_key, deps.gate
        if pr_info:
            jira_blocks.append(("para", f"Pull request: {pr_info.url}"))
            title = f"PR #{pr_info.number} (DebugAssist)"
            url = pr_info.url
            gate.gated(
                "jira.link", lambda: deps.jira.link(key, url, title), run_id=state.run_id, detail={"key": key}
            )
        blocks = jira_blocks or [("para", f"DebugAssist outcome: {ship.outcome}")]
        gate.gated(
            "jira.comment", lambda: deps.jira.comment(key, blocks), run_id=state.run_id, detail={"key": key}
        )
        to = "In Review" if pr_info else "In Progress"
        gate.gated(
            "jira.transition",
            lambda: deps.jira.transition(key, to),
            run_id=state.run_id,
            detail={"key": key, "to": to},
        )
    # Link the PR / ticket back to the user-facing issue (Vitals or BugDrop).
    links: list[tuple[str, str | None, str | None]] = (
        [("jira", tr.jira_url, tr.jira_key)] if tr and tr.jira_url and tr.jira_url.startswith("http") else []
    )
    if pr_info:
        links.append(("pr", pr_info.url, f"PR #{pr_info.number} (DebugAssist)"))
    notes += _link_source(deps, state, links, ship.outcome)
    notes += _comment_app_issue(deps, state, pr_info, ship.outcome)
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
