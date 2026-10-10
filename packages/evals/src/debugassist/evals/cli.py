"""`debugassist eval …`: run catalog bugs end to end, replay decisions, write the report."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from statistics import mean
from typing import Annotated, Any, cast

import typer

from debugassist.core.policy import ROOT
from debugassist.evals import run as eval_run

app = typer.Typer(
    no_args_is_help=True, help="Evaluation: catalog runs, decision replay (E1), ablations, reports"
)


def _ids(bugs: str | None) -> list[str]:
    return (
        eval_run.catalog_ids()
        if not bugs or bugs == "all"
        else [b.strip() for b in bugs.split(",") if b.strip()]
    )


def _per_run_usd() -> float:
    """Mean LLM + Clef cost of past live runs that produced an RCA (the basis for estimates)."""
    costs: list[float] = []
    for f in (ROOT / ".data" / "runs").glob("*/state.json"):
        s = json.loads(f.read_text())
        rca = cast(dict[str, Any], s.get("rca") or {})
        if s.get("llm_mode") == "live" and rca.get("output"):
            costs.append(sum(cast(dict[str, float], s.get("costs") or {}).values()))
    return (mean(costs) if costs else 0.3) + 0.01  # + Clef (≈ 20 decisions × $0.0003)


@app.command()
def estimate(
    bugs: Annotated[str | None, typer.Option(help="comma list or 'all'")] = None,
    configs: Annotated[str, typer.Option()] = "routed",
    seeds: Annotated[int, typer.Option()] = 3,
) -> None:
    """Estimated cost of an eval matrix, from the mean cost of past live runs."""
    e = eval_run.estimate(_ids(bugs), configs.split(","), seeds, _per_run_usd())
    typer.echo(json.dumps(e))


@app.command("run")
def run_cmd(
    bugs: Annotated[str | None, typer.Option(help="comma list of catalog ids, or 'all'")] = None,
    configs: Annotated[str, typer.Option(help=f"comma list of: {', '.join(eval_run.CONFIGS)}")] = "routed",
    seeds: Annotated[int, typer.Option(help="runs per configuration")] = 3,
    until: Annotated[
        str,
        typer.Option(
            help="last node to run ('' = whole pipeline); ship_gate keeps the fix ↔ validate retry loop"
        ),
    ] = "ship_gate",
    hidden: Annotated[bool, typer.Option(help="run the catalog's hidden tests on each fix")] = True,
    wipe: Annotated[
        bool, typer.Option(help="wipe Vitals/BugDrop data between bugs (clean discovery)")
    ] = True,
    max_usd: Annotated[float, typer.Option(help="refuse to start if the estimate is above this")] = 5.0,
    reserve_usd: Annotated[
        float, typer.Option(help="stop before the next bug when the OpenRouter key has less credit left")
    ] = 0.0,
    arm: Annotated[str, typer.Option(help="label for this code version in reports, e.g. cross-repo")] = "",
) -> None:
    """Run catalog bugs end to end per configuration and seed; score and label every run."""
    ids, cfgs = _ids(bugs), configs.split(",")
    e = eval_run.estimate(ids, cfgs, seeds, _per_run_usd())
    typer.echo(f"plan: {e['runs']} runs ≈ ${e['total_usd']} (≈ ${e['per_run_usd']}/run)")
    if e["total_usd"] > max_usd:
        typer.echo(f"estimate above --max-usd {max_usd}; raise it explicitly to proceed")
        raise typer.Exit(2)
    out = asyncio.run(
        eval_run.evaluate(
            ids,
            cfgs,
            seeds,
            until=until or None,
            hidden=hidden,
            wipe=wipe,
            reserve_usd=reserve_usd,
            arm=arm,
            log=typer.echo,
        )
    )
    typer.echo(f"results: {out / 'results.jsonl'}")


@app.command()
def langfuse(
    runs: Annotated[str, typer.Option(help="comma list of evals/runs/<stamp> dirs")],
) -> None:
    """Send eval runs to Langfuse as experiments: one item per run with its scores (`make langfuse` first)."""
    from debugassist.core import tracing
    from debugassist.evals import langfuse_export

    out = langfuse_export.export([Path(d) for d in runs.split(",")])
    typer.echo(f"{out['items']} runs → Langfuse ({tracing.langfuse_url()}), experiments:")
    for name in out["experiments"]:
        typer.echo(f"  {name}")


@app.command()
def context(
    runs: Annotated[str, typer.Option(help="comma list of evals/runs/<stamp> dirs")],
    model: Annotated[str, typer.Option(help="only runs whose RCA used this model")] = "",
    name: Annotated[
        str, typer.Option(help="suffix for the output files, e.g. an arm: context-<name>.md")
    ] = "",
) -> None:
    """Where agents' input tokens go (fixed prefix, re-sent tool results, own messages) — writes
    evals/reports/<date>/context[-<name>].md and .json."""
    import json
    from datetime import UTC, datetime

    from debugassist.evals import context as ctx

    ids: list[str] = []
    for d in runs.split(","):
        for line in (Path(d) / "results.jsonl").read_text().splitlines():
            row = json.loads(line)
            if row.get("run_id") and not row.get("excluded") and model in str(row.get("model") or ""):
                ids.append(row["run_id"])
    summary = ctx.summarize(ctx.audit(ids))
    out = ROOT / "evals" / "reports" / datetime.now(UTC).strftime("%Y-%m-%d")
    out.mkdir(parents=True, exist_ok=True)
    stem = f"context-{name}" if name else "context"
    summary["runs"] = len(ids)
    (out / f"{stem}.md").write_text(ctx.report(summary, len(ids)))
    (out / f"{stem}.json").write_text(json.dumps(summary, indent=2))
    typer.echo(f"context audit of {len(ids)} runs: {out / f'{stem}.md'}")


@app.command()
def rescore(eval_dir: Annotated[Path, typer.Argument(help="evals/runs/<stamp>")]) -> None:
    """Recompute each run's score from its saved state with the current scorer (hidden-test results kept)."""
    import json

    from debugassist.evals import score
    from debugassist.scenarios.catalog import get_bug

    path = eval_dir / "results.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    keep = ("hidden_tests", "hidden_detail", "config", "seed", "issue", "deduped_from", "labelled_decisions")
    out: list[dict[str, object]] = []
    for row in rows:
        if row.get("run_id") and (score.RUNS / row["run_id"] / "state.json").is_file():
            fresh = score.score_run(
                row["run_id"], get_bug(row["bug"]), float(row.get("clef_usd") or 0), False
            )
            row = {**row, **fresh, **{k: row[k] for k in keep if k in row}}
        out.append(row)
    path.write_text("".join(json.dumps(r, default=str) + "\n" for r in out))
    typer.echo(f"rescored {sum(1 for r in out if r.get('run_id'))} runs in {path}")


@app.command()
def label(eval_dir: Annotated[Path, typer.Argument(help="evals/runs/<stamp>")]) -> None:
    """(Re)label the decisions of every run in an eval directory from the catalog."""
    from debugassist.core.ledger import Ledger
    from debugassist.core.settings import get_settings
    from debugassist.evals import labels
    from debugassist.scenarios.catalog import get_bug

    async def main() -> int:
        ledger = await Ledger.open(get_settings().database_url)
        n = 0
        try:
            for line in (eval_dir / "results.jsonl").read_text().splitlines():
                r = json.loads(line)
                if r.get("run_id"):
                    n += await labels.label_run(ledger, r["run_id"], get_bug(r["bug"]))
        finally:
            await ledger.close()
        return n

    typer.echo(f"labelled {asyncio.run(main())} decisions")


@app.command()
def replay(
    backends: Annotated[
        str, typer.Option(help="comma list of clef, clef-flash, llm, rules")
    ] = "clef,clef-flash,llm,rules",
    limit: Annotated[int, typer.Option(help="at most this many labelled decisions")] = 400,
) -> None:
    """E1: re-ask every catalog-labelled decision to each decider and score it."""
    from debugassist.core.ledger import Ledger
    from debugassist.core.settings import get_settings
    from debugassist.evals import replay as rp
    from debugassist.scenarios.catalog import load_catalog

    async def main() -> Path:
        ledger = await Ledger.open(get_settings().database_url)
        try:
            rows = [r for r in await ledger.list() if r.outcome_source == "catalog"][:limit]
        finally:
            await ledger.close()
        typer.echo(f"replaying {len(rows)} labelled decisions × {backends}")
        return rp.save(await rp.replay(rows, load_catalog(), backends.split(",")))

    typer.echo(f"results: {asyncio.run(main())}")


@app.command()
def report(
    runs: Annotated[
        str | None, typer.Option(help="comma list of evals/runs/<stamp> dirs (default: all)")
    ] = None,
    notes: Annotated[Path | None, typer.Option(help="markdown file placed at the top of the report")] = None,
) -> None:
    """Write evals/reports/<date>/report.md + CSV + charts from eval results, E1 replays and the ledger."""
    from debugassist.core.ledger import Ledger
    from debugassist.core.settings import get_settings
    from debugassist.decisions.templates import load_templates
    from debugassist.evals import metrics
    from debugassist.evals import report as rep

    base = ROOT / "evals" / "runs"
    dirs = (
        [Path(p) for p in runs.split(",")]
        if runs
        else sorted(d for d in base.glob("*") if d.is_dir() and d.name != "e1")
    )
    e1 = sorted((base / "e1").glob("*.jsonl")) if (base / "e1").is_dir() else []

    # Decisions and replays count only the runs this report covers (not every labelled run in the ledger).
    run_ids = {r["run_id"] for r in rep.load_results(dirs) if r.get("run_id") and not r.get("excluded")}

    async def points() -> list[metrics.Point]:
        ledger = await Ledger.open(get_settings().database_url)
        try:
            rows = [r for r in await ledger.list() if getattr(r, "run_id", None) in run_ids]
            return metrics.points(rows, source="catalog")
        finally:
            await ledger.close()

    taus = {t.id: t.policy.tau_high for t in load_templates().values()}
    out = rep.write(
        dirs, e1, asyncio.run(points()), taus, notes.read_text() if notes else "", run_ids=run_ids
    )
    typer.echo(f"report: {out / 'report.md'}")
