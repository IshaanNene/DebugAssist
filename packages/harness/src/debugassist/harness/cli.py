"""`debugassist harness …`: agent types, the marketplace, packaging and workers."""

from __future__ import annotations

import asyncio
import json
from typing import Annotated

import typer

from debugassist.harness import agent_types, domains, launcher, marketplace

app = typer.Typer(no_args_is_help=True, help="Agent types, marketplace, packaging (PEX, images) and workers")


@app.command("agent-types")
def list_agent_types() -> None:
    """Agent types, what they match and what they load."""
    for name, t in agent_types.all_types().items():
        typer.echo(f"{name:16} {t.description}")
        typer.echo(
            f"{'':16} match {t.match.model_dump(exclude_defaults=True)} · priority {t.priority} · image {t.runtime_image}"
        )
        typer.echo(
            f"{'':16} skills {t.skills} · ladder {t.validation.ladder} · marketplace@{t.marketplace_ref}"
        )


@app.command()
def resolve(issue: Annotated[str, typer.Argument(help="VIT-… or BD-…")]) -> None:
    """Which agent type an issue gets, and why."""
    info = launcher.peek(issue)
    t, why = agent_types.resolve(**info)
    typer.echo(f"{issue}: {t.name} ({why}); {info}")


@app.command("lint-skills")
def lint_skills(
    ref: Annotated[str, typer.Option(help="marketplace git ref (default: working tree)")] = "working",
) -> None:
    """Check the marketplace: 5 plugins, skill frontmatter, token budgets, no evaluation answers."""
    root = marketplace.fetch(ref)
    problems = marketplace.lint(root, agent_types.all_types())
    ps, ss = marketplace.plugins(root), marketplace.skills(root)
    typer.echo(
        f"{len(ps)} plugins · {len(ss)} skills · {len(domains.load_all(root))} domains (marketplace@{ref})"
    )
    for s in ss.values():
        typer.echo(f"  {s.plugin:18} {s.name:18} ~{s.tokens} tokens")
    for p in problems:
        typer.echo(f"  ✗ {p}")
    raise typer.Exit(1 if problems else 0)


@app.command()
def fetch(ref: Annotated[str, typer.Argument(help="git ref to materialise")]) -> None:
    """Materialise the marketplace at a git ref (what a pinned agent type or a runtime image uses)."""
    typer.echo(marketplace.fetch(ref))


@app.command()
def pex(
    agent_type: Annotated[str, typer.Argument()],
    upload: Annotated[bool, typer.Option(help="store it in MinIO")] = True,
) -> None:
    """Build the agent type's PEX (linux) and store it in MinIO."""
    path = launcher.build_pex(agent_type)
    typer.echo(f"built {path} ({path.stat().st_size / 1e6:.0f} MB)")
    if upload:
        typer.echo(f"uploaded {launcher.upload_pex(path, agent_type)}")


@app.command()
def image(agent_type: Annotated[str, typer.Argument()]) -> None:
    """Build the agent type's runtime image from its PEX."""
    typer.echo(f"built {launcher.build_image(agent_type)}")


@app.command("run")
def run_container(
    issue: Annotated[str, typer.Argument()],
    agent_type: Annotated[str | None, typer.Option(help="force an agent type")] = None,
    args: Annotated[
        str, typer.Option(help='extra `debugassist run` args, e.g. "--llm mock --until classify_rca"')
    ] = "",
) -> None:
    """Run the pipeline for an issue inside its agent type's runtime container."""
    info = launcher.peek(issue)
    t, why = agent_types.resolve(**info, override=agent_type)
    typer.echo(f"{issue} → {t.name} ({why}) in {t.runtime_image}")
    raise typer.Exit(launcher.run_in_container(t.name, issue, args.split()))


@app.command()
def enqueue(
    issue: Annotated[str, typer.Argument()],
    agent_type: Annotated[str | None, typer.Option()] = None,
    args: Annotated[str, typer.Option(help="extra `debugassist run` args")] = "",
) -> None:
    """Queue an issue for a worker (Redis + Arq)."""
    from debugassist.harness import worker

    typer.echo(f"queued job {asyncio.run(worker.enqueue(issue, agent_type, args.split()))}")


@app.command("worker")
def run_worker(burst: Annotated[bool, typer.Option(help="exit when the queue is empty")] = False) -> None:
    """Process queued issues (each in its agent type's runtime container)."""
    from debugassist.harness import worker

    w = worker.make_worker(burst=burst)
    w.run()
    typer.echo(json.dumps({"jobs_complete": w.jobs_complete, "jobs_failed": w.jobs_failed}))
