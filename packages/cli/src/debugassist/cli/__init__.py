"""`debugassist` CLI: decisions, scenarios (and, later, runs)."""

from __future__ import annotations

import typer

from debugassist.decisions.cli import decide, list_templates, modes
from debugassist.evals.cli import app as eval_app
from debugassist.harness.cli import app as harness_app
from debugassist.pipeline.cli import ask, feedback_cmd, fix_diff, open_run, run, watch
from debugassist.pipeline.report import report
from debugassist.scenarios.cli import app as scenario_app

app = typer.Typer(no_args_is_help=True, help="DebugAssist: crash or bug report → RCA → validated PR")
app.command()(decide)
app.command("templates")(list_templates)
app.command()(modes)
app.command()(run)
app.command()(report)
app.command()(watch)
app.command("fix-diff")(fix_diff)
app.command()(ask)
app.command("open")(open_run)
app.command("feedback")(feedback_cmd)
app.add_typer(scenario_app, name="scenario")
app.add_typer(harness_app, name="harness")
app.add_typer(eval_app, name="eval")
