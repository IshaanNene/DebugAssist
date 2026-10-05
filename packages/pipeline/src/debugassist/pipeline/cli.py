"""`debugassist run <issue>`: drive one issue through the pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import sys
from collections import Counter
from typing import Annotated, Any, cast

import httpx
import typer
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from pydantic import BaseModel

from debugassist.core import tracing
from debugassist.core.evidence import EvidenceItem
from debugassist.core.policy import ROOT
from debugassist.decisions.policy import Band
from debugassist.integrations.github import GitHubMock
from debugassist.integrations.jira import JiraMock
from debugassist.pipeline import postmerge
from debugassist.pipeline import state as state_module
from debugassist.pipeline.deps import build_deps, new_run_id
from debugassist.pipeline.graph import build_graph
from debugassist.pipeline.state import RunState


def _decision_backends(run_id: str) -> str | None:
    """Which backend made this run's decisions — and why any fell back (a silent fallback looks normal)."""
    db = ROOT / ".data" / "debugassist.db"
    if not db.is_file():
        return None
    with sqlite3.connect(db) as con:
        rows = con.execute(
            "select backend, fallback_reason from decision_ledger where run_id = ?", (run_id,)
        ).fetchall()
    if not rows:
        return None
    counts = Counter(str(b) for b, _ in rows)
    line = " · ".join(f"{n} {b}" for b, n in counts.most_common())
    reasons = [str(r) for _, r in rows if r and r != "circuit open"]
    if reasons:
        line += f"  ⚠ fell back: {reasons[0][:110]}"
    return line


def _summary(s: RunState) -> None:
    typer.echo("")
    typer.echo(f"run {s.run_id}: {s.status}")
    if s.issue:
        typer.echo(f"  issue     {s.issue.id} {s.issue.title[:90]}")
    if s.triage:
        typer.echo(
            f"  triage    {s.triage.priority} · {s.triage.owner_team} ({s.triage.owner_source}) · on-call {s.triage.oncall} · Jira {s.triage.jira_key} {s.triage.jira_url or ''}"
        )
        if s.triage.dedup:
            dd = s.triage.dedup
            typer.echo(f"  dedup     D02 → {dd.get('chosen')} (p={dd.get('p') or 0:.2f}, {dd.get('action')})")
    if (dec := _decision_backends(s.run_id)) is not None:
        typer.echo(f"  decisions {dec}")
    if s.evidence:
        kept = len(s.evidence)
        dropped = [p for p in s.evidence_pruned if "id" in p]
        typer.echo(f"  evidence  {kept} items kept · {len(dropped)} pruned by D3/budget")
    if s.screenshots:
        sh = s.screenshots
        typer.echo(
            f"  screens   D04 screen={sh.get('screen')} · blank p={sh.get('blank_screen')} · abnormal battery p={sh.get('abnormal_battery')}"
        )
    if s.agent_type:
        typer.echo(f"  agent     {s.agent_type} ({s.agent_type_reason})")
    if s.rca and s.rca.output:
        o = s.rca.output
        typer.echo(
            f"  RCA       {o.category} · {o.location.file} → {o.location.function} · {len(o.claims)} claims · {s.rca.llm.get('turns')} turns ({s.rca.llm.get('mode')})"
        )
        typer.echo(f"            {o.summary[:300]}")
    if s.mitigation:
        typer.echo(f"  mitigate  {s.mitigation.action}: {s.mitigation.detail}")
    if s.fix_plan:
        fp = s.fix_plan
        typer.echo(
            f"  plan      D12 {fp.location.get('action')} → {', '.join(fp.focus) or '-'} ({fp.candidates} candidates)"
            f" · D13 {fp.strategy.get('choice')} ({fp.strategy.get('action')}) · D14 {fp.tier.get('choice')} ({fp.tier.get('action')}) → ladder {' → '.join(fp.ladder) or '-'}"
            + (f" · skip: {fp.skip}" if fp.skip else "")
        )
        if fp.suspect_commits:
            typer.echo(
                "            commits in window: "
                + "; ".join(f"{c['sha']} {c['subject']}" for c in fp.suspect_commits[:3])
            )
    for fa in s.fix_attempts:
        reproduce = [cast(dict[str, Any], v) for k, v in fa.llm.items() if k.startswith("reproduce")]
        rp = reproduce[-1] if reproduce else {}
        fx = fa.llm.get("fix", {})
        typer.echo(
            f"  fix #{fa.n}    repro {'✓' if fa.repro_verified else '✗'} [{fa.tier or '/'.join(t['tier'] for t in fa.tiers_tried) or '-'}] {fa.repro.test_file if fa.repro else '-'} "
            f"({rp.get('turns')} turns) · fix {fx.get('status', '-')} ({fx.get('turns')} turns) · files: {', '.join(fa.files)}"
        )
    if s.validation:
        v = s.validation
        fb = v.failing_before.exit_code if v.failing_before else None
        pa = v.passing_after.exit_code if v.passing_after else None
        typer.echo(
            f"  validate  passed={v.passed} · failing-before exit={fb} · passing-after exit={pa} · suite exit={v.suite.exit_code if v.suite else None}"
            + (f" · CI checks exit={v.static.exit_code}" if v.static else "")
        )
    if s.ship:
        typer.echo(f"  ship      {s.ship.outcome}")
    if s.pr:
        typer.echo(f"  PR        {s.pr.url} ({s.pr.branch} → {s.pr.base}, {s.pr.mode})")
    for n in s.notifications:
        if n.get("kind") == "chat":
            typer.echo(f"  chat      {n.get('to')} ({n.get('mode')}): {str(n.get('title', ''))[:90]}")
        elif n.get("kind") == "link":
            typer.echo(f"  link      {n.get('issue')} ← {n.get('url')} ({n.get('result')})")
    if s.watch:
        typer.echo(
            f"  watch     {s.watch.status} — after merge + `make deploy`: debugassist watch {s.run_id}"
        )
    typer.echo(f"  cost      ${sum(s.costs.values()):.4f} LLM · {sum(s.timings_ms.values()) / 1000:.0f}s")
    for e in s.errors[:1]:
        typer.echo(f"  error     {e}")


# Types stored in run checkpoints (LangGraph only deserializes allow-listed classes).
CHECKPOINT_TYPES = [
    *(
        (state_module.__name__, name)
        for name, obj in vars(state_module).items()
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj.__module__ == state_module.__name__
    ),
    (EvidenceItem.__module__, "EvidenceItem"),
    (Band.__module__, "Band"),
]


def _latest_issue(vitals_url: str = "http://localhost:8100") -> str:
    open_crashes = [
        i
        for i in httpx.get(f"{vitals_url}/api/issues", timeout=10).raise_for_status().json()
        if i.get("status") == "open" and i.get("kind") == "crash"
    ]
    if not open_crashes:
        raise typer.BadParameter("Vitals has no open crash issue (trigger a scenario first)")
    return str(open_crashes[0]["id"])


def run(
    issue: Annotated[
        str | None,
        typer.Argument(help="Vitals issue (VIT-…), BugDrop report (BD-…), or 'latest' (newest open crash)"),
    ] = None,
    issue_opt: Annotated[str | None, typer.Option("--issue", help="same as the positional issue")] = None,
    agent_type: Annotated[
        str | None,
        typer.Option(help="force an agent type (web-crash, backend-error, perf-regression, user-bug-report)"),
    ] = None,
    mode: Annotated[str, typer.Option(help="autonomous | supervised (pauses for approvals)")] = "autonomous",
    llm: Annotated[str, typer.Option(help="live | replay | mock")] = "live",
    replay_from: Annotated[
        str | None, typer.Option(help="run id whose recorded LLM results to replay")
    ] = None,
    resume: Annotated[
        str | None, typer.Option(help="run id to resume from its last completed node (checkpoint)")
    ] = None,
    until: Annotated[
        str | None, typer.Option(help="stop after this step, e.g. classify_rca (cheap stage-by-stage runs)")
    ] = None,
    from_node: Annotated[
        str | None,
        typer.Option(help="with --resume: rewind to the checkpoint just before this node's first run"),
    ] = None,
) -> None:
    """Run the pipeline on one issue: triage → RCA → mitigation → fix → validation → PR."""

    # Live agent progress (turns, tool calls, retries, watchdog) on the console.
    progress = logging.getLogger("debugassist.progress")
    if not progress.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        progress.addHandler(handler)
        progress.setLevel(logging.INFO)
        progress.propagate = False

    def _last_node(values: dict[str, Any]) -> str | None:
        """Runs stopped before `stopped_after` existed: the last node that recorded a timing."""
        timings = list(cast(dict[str, int], values.get("timings_ms") or {}))
        return timings[-1] if timings else None

    issue = issue or issue_opt
    if not issue and not resume:
        raise typer.BadParameter("give an issue (positional or --issue) or --resume <run>")

    async def main() -> RunState:
        nonlocal issue
        if issue == "latest":
            issue = _latest_issue()
        run_id = resume or new_run_id(issue or "resume")
        deps = await build_deps(run_id, mode=mode, llm_mode=llm, replay_from=replay_from)
        if until:
            deps.extra["until"] = until
        if agent_type:
            from debugassist.harness import agent_types

            agent_types.load(agent_type)  # fail fast on a typo
            deps.extra["agent_type"] = agent_type
        typer.echo(f"run {run_id} ({mode}, LLM {llm}); artifacts in .data/runs/{run_id}/")
        (ROOT / ".data").mkdir(exist_ok=True)
        if tracing.setup():
            typer.echo(f"  tracing → {tracing.phoenix_url()} (project {tracing.PROJECT})")
        with (
            tracing.session(run_id, issue=issue),
            tracing.span(f"run {run_id}", kind="agent", **{"session.id": run_id, "issue": issue}),
        ):
            deps.extra["trace_id"] = tracing.current_trace_id()
            result = await _invoke(run_id, deps)
        tracing.shutdown()
        if deps.engine.ledger is not None:
            await deps.engine.ledger.close()
        return RunState.model_validate(result)

    async def _invoke(run_id: str, deps: Any) -> dict[str, Any]:
        async with AsyncSqliteSaver.from_conn_string(str(ROOT / ".data" / "checkpoints.sqlite")) as saver:
            saver.serde = JsonPlusSerializer(allowed_msgpack_modules=CHECKPOINT_TYPES)
            builder = build_graph(deps, log=lambda m: typer.echo(f"  {m}"))
            graph: Any = builder.compile(checkpointer=saver)  # pyright: ignore[reportUnknownMemberType]
            cfg: RunnableConfig = {"configurable": {"thread_id": run_id}, "recursion_limit": 60}
            start = (
                None
                if resume
                else RunState.model_validate(
                    {"run_id": run_id, "issue_ref": issue, "mode": mode, "llm_mode": llm}
                )
            )
            if resume and from_node:
                history = [h async for h in graph.aget_state_history(cfg)]  # newest first
                before = [h for h in history if h.next == (from_node,)]
                if not before:
                    raise typer.BadParameter(f"run {run_id} never reached {from_node}")
                cfg = RunnableConfig(configurable=before[-1].config["configurable"], recursion_limit=60)
            elif resume:
                # A run stopped by --until continues from the node that stopped it.
                snap = await graph.aget_state(cfg)
                values = cast(dict[str, Any], snap.values)
                stopped_after = values.get("stopped_after") or _last_node(values)
                if values.get("status") == "stopped" and not snap.next and stopped_after:
                    cfg = await graph.aupdate_state(
                        cfg, {"status": "running", "stopped_after": None}, as_node=stopped_after
                    )
            result: dict[str, Any] = await graph.ainvoke(start, cfg)
            cfg = {"configurable": {"thread_id": run_id}, "recursion_limit": 60}  # later resumes: latest
            while "__interrupt__" in result:
                ask = result["__interrupt__"][0].value
                approved = typer.confirm(f"  ⏸ {ask.get('question')}", default=False)
                result = await graph.ainvoke(Command(resume=approved), cfg)
        return result

    _summary(asyncio.run(main()))


def watch(
    run_id: Annotated[str, typer.Argument(help="run id of a run that opened a PR")],
    min_sessions: Annotated[int, typer.Option(help="sessions needed after the deploy before deciding")] = (
        postmerge.MIN_SESSIONS
    ),
    approve_flag_restore: Annotated[
        bool, typer.Option(help="approve restoring a rolled-back flag (policy: approval)")
    ] = False,
) -> None:
    """Post-merge check (D17): after merge + `make deploy`, is the issue gone? Resolve or reopen."""

    async def main() -> RunState:
        path = ROOT / ".data" / "runs" / run_id / "state.json"
        if not path.is_file():
            raise typer.BadParameter(f"no run {run_id}")
        s = RunState.model_validate_json(path.read_text())
        if s.watch is None:
            raise typer.BadParameter(f"run {run_id} opened no PR; nothing to watch")
        deps = await build_deps(run_id, mode=s.mode, llm_mode="mock")
        # Act through the same backends the run used: a mock ticket or PR is never looked up live.
        if s.triage and s.triage.jira_mode == "mock":
            deps.jira = JiraMock()
        if s.pr and s.pr.mode == "mock":
            deps.github = GitHubMock()
        try:
            s.watch = await postmerge.check(
                s, deps, min_sessions=min_sessions, approve_flag_restore=approve_flag_restore
            )
        finally:
            if deps.engine.ledger is not None:
                await deps.engine.ledger.close()
        if s.watch.status != "watching":
            s.status = "done"
        path.write_text(s.model_dump_json(indent=2))
        with (path.parent / "watch.jsonl").open("a") as f:
            f.write(s.watch.model_dump_json() + "\n")
        return s

    s = asyncio.run(main())
    w = s.watch
    assert w
    typer.echo(f"run {run_id}: {w.status}" + (f" — {w.reason}" if w.reason else ""))
    if w.deploy:
        typer.echo(f"  deploy    {w.deploy.get('ref')} ({w.deploy.get('sha')}) at {w.deploy.get('at')}")
    if w.after:
        typer.echo(
            f"  rate      before {w.before.get('rate')} ({w.before.get('sessions')} sessions) → after {w.after.get('rate')} ({w.after.get('sessions')} sessions)"
        )
    if w.decision:
        typer.echo(
            f"  D17       {w.decision.get('action')} (p={w.decision.get('p')}, {w.decision.get('band')})"
        )
    for a in w.actions:
        typer.echo(f"  action    {a}")


def fix_diff(
    run_id: Annotated[str, typer.Argument(help="run whose fix to revise")],
    instruction: Annotated[str, typer.Argument(help='e.g. "use the existing clamp helper"')],
    job: Annotated[
        str | None, typer.Option(help="write the result to .data/runs/<run>/jobs/<job>.json")
    ] = None,
) -> None:
    """Diff fixer: revise the run's fix per one instruction, re-validate, commit, push and comment."""
    from debugassist.pipeline import postpr

    try:
        entry = asyncio.run(postpr.fix_diff(run_id, instruction))
    except (FileNotFoundError, ValueError) as exc:
        entry = {"status": "error", "reason": str(exc)}
    if job:
        d = ROOT / ".data" / "runs" / run_id / "jobs"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{job}.json").write_text(json.dumps(entry, indent=2, default=str))
    typer.echo(
        f"diff fixer: {entry.get('status')}" + (f" — {entry.get('reason')}" if entry.get("reason") else "")
    )
    if entry.get("commit"):
        typer.echo(
            f"  commit {entry['commit']} {entry.get('title')} · pushed={entry.get('pushed')} · commented={entry.get('commented')}"
        )


def ask(
    run_id: Annotated[str, typer.Argument(help="run to ask about")],
    message: Annotated[str, typer.Argument(help="your question or correction")],
    session: Annotated[str | None, typer.Option(help="resume a chat session")] = None,
    correction: Annotated[
        bool, typer.Option(help="this corrects the analysis: route it through D18")
    ] = False,
) -> None:
    """Ask AI about a run (answers cite evidence ids; sessions are resumable)."""
    from debugassist.pipeline import postpr

    r = asyncio.run(postpr.ask(run_id, message, session, correction=correction))
    typer.echo(r["answer"])
    typer.echo(
        f"\n  session {r['session_id']} · cited {', '.join(r['evidence_ids']) or '-'} · ${r['cost_usd']:.4f} ({r['mode']})"
    )
    if r.get("routed"):
        typer.echo(f"  D18: {r['routed'].get('kind')} → {r['routed'].get('action')}")


def open_run(run_id: Annotated[str, typer.Argument(help="run to open locally")]) -> None:
    """Open in your machine: devcontainer + compose override pinned to the bad release and the fix."""
    from debugassist.pipeline import postpr

    r = postpr.open_env(run_id)
    typer.echo(f"VS Code:      {r['vscode']}")
    typer.echo(f"devcontainer: {r['devcontainer']}  (Dev Containers: Open Folder in Container)")
    typer.echo(
        f"bad release:  {r['bad_ref']} · fix branch {r['fix_branch']} · flags {json.dumps(r['flags'])}"
    )
    for c in r["commands"]:
        typer.echo(f"  $ {c}")


def feedback_cmd(
    run_id: Annotated[str, typer.Argument(help="run the feedback is about")],
    reaction: Annotated[str, typer.Option(help="up | down")] = "down",
    target: Annotated[str, typer.Option(help="rca | claim:<n> | fix | chat")] = "rca",
    comment: Annotated[str, typer.Option(help="the correction, if any")] = "",
) -> None:
    """Record a reaction/correction and route it through D18 (labels, skill update, prompt log, human)."""

    async def main() -> dict[str, Any]:
        from debugassist.pipeline import feedback, postpr

        state, _ = postpr._load(run_id)  # pyright: ignore[reportPrivateUsage]
        deps = await postpr._deps(state)  # pyright: ignore[reportPrivateUsage]
        try:
            return await feedback.route(
                state, deps, {"target": target, "reaction": reaction, "comment": comment}
            )
        finally:
            if deps.engine.ledger is not None:
                await deps.engine.ledger.close()

    r = asyncio.run(main())
    typer.echo(json.dumps(r, indent=2, default=str))
