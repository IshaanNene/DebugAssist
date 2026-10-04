"""`debugassist` CLI: decisions, scenarios (and, later, runs)."""

from __future__ import annotations

import typer

from debugassist.decisions.cli import decide, list_templates, modes
from debugassist.scenarios.cli import app as scenario_app

app = typer.Typer(no_args_is_help=True, help="DebugAssist: crash or bug report → RCA → validated PR")
app.command()(decide)
app.command("templates")(list_templates)
app.command()(modes)
app.add_typer(scenario_app, name="scenario")
