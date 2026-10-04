"""`debugassist scenario …`: list, inject, trigger and reset catalog bugs on the local stack."""

from __future__ import annotations

import asyncio
import json
import subprocess
import time
from typing import Annotated, Any

import typer

from debugassist.scenarios import injector
from debugassist.scenarios.catalog import get_bug, load_catalog
from debugassist.scenarios.environment import Environment

app = typer.Typer(
    no_args_is_help=True, help="Bug scenarios on the local MiniRide stack (ground truth stays local)"
)


def log(msg: str) -> None:
    typer.echo(f"  {msg}")


@app.command("list")
def list_bugs() -> None:
    """List catalog bugs."""
    for b in load_catalog().values():
        typer.echo(f"{b.id}  {b.priority}  {b.category:<12} {b.component:<16} {b.title}")


@app.command()
def verify(bug_ids: Annotated[list[str] | None, typer.Argument()] = None) -> None:
    """Check catalog integrity: regression applies, hidden test fails on it, fix passes."""
    from debugassist.scenarios.verify import verify as run_verify

    failed = 0
    for bug_id in bug_ids or list(load_catalog()):
        v = run_verify(get_bug(bug_id))
        typer.echo(f"{'PASS' if v.ok else 'FAIL'} {v.bug}")
        for c in v.checks:
            typer.echo(f"   {'✓' if c.ok else '✗'} {c.name}")
            if not c.ok and c.detail:
                typer.echo("     " + c.detail.strip().replace("\n", "\n     ")[-1200:])
        failed += not v.ok
    if failed:
        raise typer.Exit(1)


@app.command()
def status() -> None:
    """Show the active scenario, if any."""
    state = injector.current()
    typer.echo(json.dumps(state, indent=2) if state else "no active scenario (clean release)")


@app.command()
def inject(
    bug_id: str, push: Annotated[bool, typer.Option(help="Push release branch + tag to GitHub")] = False
) -> None:
    """Inject a bug: regression commits on a release branch, rebuild, flags/toxics/incidents."""
    bug = get_bug(bug_id)
    typer.echo(f"injecting {bug.id}: {bug.title}")
    injector.inject(bug, Environment(), push=push, log=log)


@app.command()
def reset(
    wipe: Annotated[bool, typer.Option(help="Also wipe Vitals, BugDrop and ride data")] = False,
) -> None:
    """Back to the clean release: main branches, baseline flags, no toxics or incidents."""
    injector.reset(Environment(), wipe=wipe, log=log)


def _duplicate_rides(minutes: int = 15) -> int:
    window = f"'{int(minutes)} minutes'"
    sql = f"SELECT count(*) FROM (SELECT session_id FROM rides WHERE created_at > now() - interval {window} GROUP BY session_id HAVING count(*) > 1) d"  # noqa: S608
    out = subprocess.run(
        [
            "docker",
            "exec",
            "debugassist-postgres-1",
            "psql",
            "-U",
            "debugassist",
            "-d",
            "miniride",
            "-Atc",
            sql,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return int(out.stdout.strip() or 0)


@app.command()
def trigger(
    bug_id: str,
    sessions: Annotated[int | None, typer.Option(help="Override the scenario's session count")] = None,
    headed: Annotated[bool, typer.Option(help="Show the browsers")] = False,
    push: Annotated[bool, typer.Option(help="Push the release branch when injecting")] = False,
) -> None:
    """Inject (if needed) and run the bug's rider scenario; report what discovery sources saw."""
    bug = get_bug(bug_id)
    env = Environment()
    state = injector.current()
    if state and state["bug"] != bug.id:
        raise typer.BadParameter(f"{state['bug']} is active; run `debugassist scenario reset` first")
    if not state:
        typer.echo(f"injecting {bug.id}: {bug.title}")
        injector.inject(bug, env, push=push, log=log)
    issues_before = {i["id"] for i in env.vitals_issues()}
    reports_before = {r["id"] for r in env.bugdrop_reports()}
    params: dict[str, Any] = dict(bug.trigger.params)
    if sessions is not None:
        params["sessions"] = sessions
    typer.echo(f"running rider scenario '{bug.trigger.scenario}' …")
    from debugassist.simulator.scenarios import run_scenario

    t0 = time.time()
    summary = asyncio.run(run_scenario(bug.trigger.scenario, params, log=log, headless=not headed))
    time.sleep(3)  # let SDK batches land
    typer.echo(f"scenario finished in {time.time() - t0:.0f}s: {json.dumps(summary, default=str)}")
    new_issues = [i for i in env.vitals_issues() if i["id"] not in issues_before]
    new_reports = [r for r in env.bugdrop_reports() if r["id"] not in reports_before]
    for i in new_issues:
        typer.echo(
            f"  Vitals  {i['id']}  {i['kind']:<9} {i['app']:<16} {i['title'][:80]}  (v{i['version']}, {i['group']['count']} events)"
        )
    for r in new_reports:
        typer.echo(
            f"  BugDrop {r['id']}  {r['app']} {r['version']}  “{r['description'][:70]}”  files={len(r['files'])}"
        )
    if bug.trigger.scenario == "weak_network_booking":
        typer.echo(f"  dispatch: {_duplicate_rides()} session(s) with duplicate rides in the last 15 min")
    if not new_issues and not new_reports:
        typer.echo("  (no new Vitals issues or BugDrop reports)")
