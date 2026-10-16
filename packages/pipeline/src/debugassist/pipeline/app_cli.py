"""`debugassist app`: the GitHub App's worker — which repositories it is on, and the poll that runs labeled issues.

`poll` takes work from two places: issues labeled `debugassist` (GITHUB_APP_LABEL) on the repositories the app
is installed on and the policy allows, and deliveries the API's /github/webhook queued in `.data/app/queue/`.
An issue already carrying the app's comment, or already run to the end, is not run again by the poll; a
webhook delivery of a fresh `labeled` event always runs. Each run is its own `debugassist run GHA:…` process,
one at a time. A run that fails is retried with backoff (MAX_ATTEMPTS in all), then the issue gets a comment
saying so; a webhook delivery stays queued (in `queue/processing/`) until its run has ended.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Annotated, Any

import typer

from debugassist.core.policy import ROOT, PolicyGate
from debugassist.core.redaction import redact_secrets
from debugassist.core.settings import get_settings
from debugassist.integrations.github_app import MARKER, GitHubApp, comment_has_marker
from debugassist.pipeline import app_intake
from debugassist.pipeline.deps import build_app

app = typer.Typer(no_args_is_help=True, help="The GitHub App: installed repositories and the issue poll")
QUEUE = ROOT / ".data" / "app" / "queue"
SEEN = ROOT / ".data" / "app" / "seen.json"
CLI = Path(sys.executable).parent / "debugassist"
NOT_ONBOARDED = f"{MARKER}not-onboarded -->"
FAILED = f"{MARKER}failed -->"
MAX_ATTEMPTS = 3
RETRY_BASE = 300.0  # seconds before the first retry; doubles after each failure
STALE_RUNNING = 4 * 3600.0


def _app() -> GitHubApp:
    a = build_app(get_settings())
    if a is None:
        raise typer.BadParameter(
            "the GitHub App is not configured: see docs/github-app.md (or DA_MODE_GITHUB_APP=mock)"
        )
    return a


def _seen() -> dict[str, Any]:
    return json.loads(SEEN.read_text()) if SEEN.is_file() else {}


def _mark(key: str, value: dict[str, Any]) -> None:
    s = _seen()
    s[key] = value
    SEEN.parent.mkdir(parents=True, exist_ok=True)
    SEEN.write_text(json.dumps(s, indent=2))


def _due(entry: dict[str, Any] | None, now: float) -> bool:
    """Whether the poll should (re)run an issue it has this record of."""
    if entry is None:
        return True
    result, at = str(entry.get("result", "")), float(entry.get("at") or 0)
    if result == "running":
        return now - at > STALE_RUNNING  # a poller that died mid-run
    if result.startswith("exit"):
        attempts = int(entry.get("attempts") or 1)
        return attempts < MAX_ATTEMPTS and now - at >= RETRY_BASE * 2 ** (attempts - 1)
    return False  # done, not onboarded, or failed for good: the issue carries a comment saying so


def pending(a: GitHubApp, gate: PolicyGate, label: str) -> list[tuple[str, int, str]]:
    """(repo, issue number, why) to run: webhook deliveries first, then labeled issues without the app's comment."""
    out: list[tuple[str, int, str]] = []
    processing = QUEUE / "processing"
    if QUEUE.is_dir():
        processing.mkdir(exist_ok=True)
        for f in sorted(QUEUE.glob("*.json")):
            f.rename(processing / f.name)  # deleted by `done_delivery` once its run ends, not before
        for f in sorted(processing.glob("*.json")):
            d = json.loads(f.read_text())
            if gate.allowed_repo(str(d["repo"])):
                out.append((str(d["repo"]), int(d["number"]), "webhook"))
            else:
                f.unlink()
    seen, now = _seen(), time.time()
    for repo in a.installed_repos():
        if not gate.allowed_repo(repo):
            continue
        for issue in a.labeled_issues(repo, label):
            key = app_intake.ref(repo, issue.number)
            if not _due(seen.get(key), now) or any(r == repo and n == issue.number for r, n, _ in out):
                continue
            if comment_has_marker(a.comments(repo, issue.number)):
                continue
            out.append((repo, issue.number, "labeled"))
    return out


def done_delivery(repo: str, number: int) -> None:
    for f in sorted((QUEUE / "processing").glob("*.json")):
        d = json.loads(f.read_text())
        if (d.get("repo"), d.get("number")) == (repo, number):
            f.unlink()


def _spawn(ref: str, llm: str) -> int:
    return subprocess.run([str(CLI), "run", ref, "--llm", llm], env=os.environ.copy(), check=False).returncode


def run_one(a: GitHubApp, repo: str, number: int, *, llm: str = "live", dry: bool = False) -> int:
    """One labeled issue through the pipeline (its own process); returns the exit code."""
    ref = app_intake.ref(repo, number)
    try:
        app_intake.ensure_checkout(a, repo)
    except app_intake.NotOnboarded as exc:
        if not any(c.lstrip().startswith(NOT_ONBOARDED) for c in a.comments(repo, number)):
            a.comment(
                repo,
                number,
                f"{NOT_ONBOARDED}\nDebugAssist can't run here yet: this repository has no "
                "`.DebugAssist/pipeline.yaml` saying how to build and test it. See "
                "https://github.com/IshaanNene/DebugAssist/blob/main/docs/github-app.md#onboarding-a-repository.",
            )
        _mark(ref, {"result": "not_onboarded", "why": str(exc)})
        return 0
    if dry:
        typer.echo(f"would run {ref}")
        return 0
    attempts = int(_seen().get(ref, {}).get("attempts") or 0) + 1
    _mark(ref, {"result": "running", "at": time.time(), "attempts": attempts})
    code = _spawn(ref, llm)
    _mark(ref, {"result": "done" if code == 0 else f"exit {code}", "at": time.time(), "attempts": attempts})
    typer.echo(f"{ref}: {'done' if code == 0 else f'exit {code} (attempt {attempts} of {MAX_ATTEMPTS})'}")
    if code and attempts >= MAX_ATTEMPTS:
        a.comment(
            repo,
            number,
            f"{FAILED}\nDebugAssist could not finish an analysis of this issue ({attempts} attempts, last exit "
            f"code {code}). The maintainers of this DebugAssist installation can see the run logs; remove and "
            "re-add the label to try again.",
        )
    return code


@app.command()
def status() -> None:
    """The repositories the app is installed on, and whether the write policy lets it act there."""
    a = _app()
    gate = PolicyGate(installed=a.installed_repos)
    for repo in a.installed_repos():
        typer.echo(f"{repo}: {'allowed' if gate.allowed_repo(repo) else 'not allowed by writes.yaml'}")


@app.command()
def poll(
    once: Annotated[bool, typer.Option(help="one pass, then exit")] = False,
    interval: Annotated[int, typer.Option(help="seconds between passes")] = 60,
    llm: Annotated[str, typer.Option(help="live | mock")] = "live",
    dry: Annotated[bool, typer.Option(help="list what would run, run nothing")] = False,
) -> None:
    """Run every labeled issue (and webhook delivery) once, one at a time."""
    a = _app()
    label = get_settings().github_app_label
    gate = PolicyGate(installed=a.installed_repos)
    while True:
        for repo, number, why in pending(a, gate, label):
            typer.echo(f"{repo}#{number} ({why})")
            try:
                run_one(a, repo, number, llm=llm, dry=dry)
            except Exception as exc:  # one repository's API error must not stop the poll
                typer.echo(
                    f"{repo}#{number}: {type(exc).__name__}: {redact_secrets(str(exc))[:300]}", err=True
                )
            finally:
                if not dry:
                    done_delivery(repo, number)
        if once:
            return
        time.sleep(interval)
