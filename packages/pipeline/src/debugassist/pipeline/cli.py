"""`debugassist run <issue>`: drive one issue through the pipeline."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

import httpx
import typer
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from pydantic import BaseModel

from debugassist.core.evidence import EvidenceItem
from debugassist.core.policy import ROOT
from debugassist.decisions.policy import Band
from debugassist.pipeline import state as state_module
from debugassist.pipeline.deps import build_deps, new_run_id
from debugassist.pipeline.graph import build_graph
from debugassist.pipeline.state import RunState


def _summary(s: RunState) -> None:
    typer.echo("")
    typer.echo(f"run {s.run_id}: {s.status}")
    if s.issue:
        typer.echo(f"  issue     {s.issue.id} {s.issue.title[:90]}")
    if s.triage:
        typer.echo(
            f"  triage    {s.triage.priority} · {s.triage.owner_team} ({s.triage.owner_source}) · on-call {s.triage.oncall} · Jira {s.triage.jira_key} {s.triage.jira_url or ''}"
        )
    if s.rca and s.rca.output:
        o = s.rca.output
        typer.echo(
            f"  RCA       {o.category} · {o.location.file} → {o.location.function} · {len(o.claims)} claims · {s.rca.llm.get('turns')} turns ({s.rca.llm.get('mode')})"
        )
        typer.echo(f"            {o.summary[:300]}")
    if s.mitigation:
        typer.echo(f"  mitigate  {s.mitigation.action}: {s.mitigation.detail}")
    for fa in s.fix_attempts:
        rp, fx = fa.llm.get("reproduce", {}), fa.llm.get("fix", {})
        typer.echo(
            f"  fix #{fa.n}    repro {'✓' if fa.repro_verified else '✗'} {fa.repro.test_file if fa.repro else '-'} "
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
        str, typer.Argument(help="Vitals issue id, e.g. VIT-1001, or 'latest' (newest open crash)")
    ],
    mode: Annotated[str, typer.Option(help="autonomous | supervised (pauses for approvals)")] = "autonomous",
    llm: Annotated[str, typer.Option(help="live | replay | mock")] = "live",
    replay_from: Annotated[
        str | None, typer.Option(help="run id whose recorded LLM results to replay")
    ] = None,
    resume: Annotated[
        str | None, typer.Option(help="run id to resume from its last completed node (checkpoint)")
    ] = None,
    from_node: Annotated[
        str | None,
        typer.Option(help="with --resume: rewind to the checkpoint just before this node's first run"),
    ] = None,
) -> None:
    """Run the pipeline on one issue: triage → RCA → mitigation → fix → validation → PR."""

    async def main() -> RunState:
        nonlocal issue
        if issue == "latest":
            issue = _latest_issue()
        run_id = resume or new_run_id(issue)
        deps = await build_deps(run_id, mode=mode, llm_mode=llm, replay_from=replay_from)
        typer.echo(f"run {run_id} ({mode}, LLM {llm}); artifacts in .data/runs/{run_id}/")
        (ROOT / ".data").mkdir(exist_ok=True)
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
            result: dict[str, Any] = await graph.ainvoke(start, cfg)
            cfg = {"configurable": {"thread_id": run_id}, "recursion_limit": 60}  # later resumes: latest
            while "__interrupt__" in result:
                ask = result["__interrupt__"][0].value
                approved = typer.confirm(f"  ⏸ {ask.get('question')}", default=False)
                result = await graph.ainvoke(Command(resume=approved), cfg)
        if deps.engine.ledger is not None:
            await deps.engine.ledger.close()
        return RunState.model_validate(result)

    _summary(asyncio.run(main()))
