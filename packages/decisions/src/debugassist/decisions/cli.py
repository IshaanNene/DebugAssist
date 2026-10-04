"""``debugassist decide`` and ``debugassist templates`` commands."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated, Any

import typer

from debugassist.core.settings import Integration, get_settings
from debugassist.decisions.engine import Decision
from debugassist.decisions.factory import BackendName, build_engine
from debugassist.decisions.schema import ClefModel
from debugassist.decisions.templates import get_template, load_templates

app = typer.Typer(no_args_is_help=True, help="Clef decision engine")


def _load_json(value: str | None) -> Any:
    if value is None:
        return None
    if value.lstrip().startswith(("{", "[", '"')):
        return json.loads(value)
    return json.loads(Path(value).read_text())


def _bar(p: float, width: int = 24) -> str:
    n = round(p * width)
    return "█" * n + "·" * (width - n)


def _print_human(d: Decision) -> None:
    typer.echo(f"{d.decision_id} v{d.template_version} · {d.backend}/{d.model} · mode={d.mode.value}")
    typer.echo(
        f"latency {d.latency_ms} ms · {d.input_tokens} input tokens · ${d.cost_usd:.6f} · {d.n_calls} call(s)"
    )
    if d.fallback_reason:
        typer.echo(f"fallback: {d.fallback_reason}")
    if d.note:
        typer.echo(f"note: {d.note}")
    for qid, probs in d.probabilities.items():
        typer.echo(f"\n  {qid} → {d.chosen[qid]}")
        for opt, p in sorted(probs.items(), key=lambda kv: -kv[1])[:8]:
            typer.echo(f"    {opt:<24} {_bar(p)} {p:.3f}")
    if d.band is not None:
        typer.echo(f"\npolicy: p={d.p:.3f} → {d.band.value} → action={d.action}")
    for item, v in d.items.items():
        typer.echo(f"  item {item}: p={v.p:.3f} → {v.band.value} → {v.action}")
    if d.second_opinion is not None:
        typer.echo("\nsecond opinion:")
        _print_human(d.second_opinion)
    if d.ledger_id:
        typer.echo(f"\nledger row {d.ledger_id}")


@app.command()
def decide(
    decision_id: Annotated[str, typer.Argument(help="Template id, e.g. D05_categorize or D05")],
    state: Annotated[str, typer.Option(help="State as JSON text or a path to a JSON file")],
    params: Annotated[str | None, typer.Option(help="Template params (JSON text or file)")] = None,
    image: Annotated[list[Path] | None, typer.Option(help="Image file (repeatable, max 4)")] = None,
    backend: Annotated[str, typer.Option(help="auto | clef | llm | local | mock")] = "auto",
    model: Annotated[str | None, typer.Option(help="Override template model: clef | clef-flash")] = None,
    run_id: Annotated[str | None, typer.Option()] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print the Decision as JSON")] = False,
    no_ledger: Annotated[bool, typer.Option(help="Do not write to the ledger")] = False,
) -> None:
    """Answer one decision template and show probabilities, policy band and action."""
    if backend not in ("auto", "clef", "llm", "local", "mock"):
        raise typer.BadParameter("backend must be auto|clef|llm|local|mock")
    if model not in (None, "clef", "clef-flash"):
        raise typer.BadParameter("model must be clef or clef-flash")
    backend_name: BackendName = backend  # pyright: ignore[reportAssignmentType]
    model_name: ClefModel | None = model  # pyright: ignore[reportAssignmentType]
    from debugassist.decisions.engine import RunContext

    async def main() -> Decision:
        settings = get_settings()
        engine = await build_engine(settings, backend_name, with_ledger=not no_ledger)
        try:
            return await engine.decide(
                decision_id,
                _load_json(state),
                list(image) if image else None,
                params=_load_json(params),
                model=model_name,
                ctx=RunContext(run_id=run_id),
            )
        finally:
            await engine.aclose()
            if engine.ledger is not None:
                await engine.ledger.close()

    d = asyncio.run(main())
    if as_json:
        typer.echo(d.model_dump_json(indent=2))
    else:
        _print_human(d)


@app.command("templates")
def list_templates(decision_id: Annotated[str | None, typer.Argument()] = None) -> None:
    """List decision templates, or show one."""
    if decision_id:
        t = get_template(decision_id)
        typer.echo(json.dumps(t.model_dump(mode="json"), indent=2))
        return
    for t in load_templates().values():
        qs = ", ".join(f"{q}:{s.type}{'*' if s.foreach else ''}" for q, s in t.questions.items())
        typer.echo(f"{t.id:<22} v{t.version} {t.model:<10} {qs}")


@app.command()
def modes() -> None:
    """Show which integrations run live vs mock."""
    s = get_settings()
    for i in Integration:
        typer.echo(f"{i.value:<8} {s.mode(i).value}")
