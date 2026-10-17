"""`debugassist app`: the GitHub App's worker — which repositories it is on, and the poll that runs labeled issues.

`poll` takes work from two places: issues labeled `debugassist` (GITHUB_APP_LABEL) on the repositories the app
is installed on and the policy allows, and deliveries the API's /github/webhook queued in `.data/app/queue/`.
An issue already carrying the app's comment, or already run to the end, is not run again by the poll; a
webhook delivery of a fresh `labeled` event always runs. Each run is its own `debugassist run GHA:…` process,
one at a time. A run that fails is retried with backoff (MAX_ATTEMPTS in all), then the issue gets a comment
saying so; a webhook delivery stays queued (in `queue/processing/`) until its run has ended.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import IO, Annotated, Any

import typer
from pydantic import BaseModel

from debugassist.core import logs
from debugassist.core.files import write_atomic
from debugassist.core.policy import ROOT, PolicyGate
from debugassist.core.redaction import redact_secrets
from debugassist.core.settings import get_settings
from debugassist.integrations.chat import Chat, ChatMessage
from debugassist.integrations.github import RateLimited
from debugassist.integrations.github_app import MARKER, GitHubApp, comment_has_marker
from debugassist.pipeline import app_intake
from debugassist.pipeline.deps import build_app, build_chat

app = typer.Typer(no_args_is_help=True, help="The GitHub App: installed repositories and the issue poll")
QUEUE = ROOT / ".data" / "app" / "queue"
SEEN = ROOT / ".data" / "app" / "seen.json"
LOCK = ROOT / ".data" / "app" / "poll.lock"
METRICS = ROOT / ".data" / "app" / "metrics.json"
RUNS_DIR = ROOT / ".data" / "runs"
CI_QUEUE = ROOT / ".data" / "app" / "ci"  # failed checks on default branches, from the webhook
FAILED_CHECK = {"failure", "timed_out"}
REVIEWS = ROOT / ".data" / "app" / "reviews"  # `@debugassist …` comments on the app's PRs, for the diff fixer
TRUSTED = {"OWNER", "MEMBER", "COLLABORATOR"}  # who may ask for a revision (it spends the operator's credit)
REFRESH = "refresh-installations"  # touched by the webhook on installation events
OUTCOMES = ROOT / ".data" / "app" / "outcomes.json"  # the last ALERT_WINDOW runs: 1 failed, 0 done
CLI = Path(sys.executable).parent / "debugassist"
NOT_ONBOARDED = f"{MARKER}not-onboarded -->"
FAILED = f"{MARKER}failed -->"
MAX_ATTEMPTS = 3
RETRY_BASE = 300.0  # seconds before the first retry; doubles after each failure
STALE_RUNNING = 4 * 3600.0
MAX_RATE_WAIT = 3600.0


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
    write_atomic(SEEN, json.dumps(s, indent=2))


def count(**increments: int) -> dict[str, float]:
    """Running totals of what the poll did (ROADMAP-100 052), in `.data/app/metrics.json` and on the API."""
    m: dict[str, float] = json.loads(METRICS.read_text()) if METRICS.is_file() else {}
    for k, v in increments.items():
        m[k] = int(m.get(k) or 0) + v
    m["updated_at"] = time.time()
    logs.event("app", "count", **increments)
    write_atomic(METRICS, json.dumps(m, indent=2, sort_keys=True))
    return m


ALERT_WINDOW = 10  # last N finished runs
ALERT_RATIO = 0.5  # alert when more than this share of them failed
ALERT_EVERY = 3600.0  # at most one alert an hour


def record_outcome(code: int, gate: PolicyGate, chat: Chat | None = None) -> bool:
    """Keep the last ALERT_WINDOW run outcomes; when more than ALERT_RATIO of them failed, page the operator once
    an hour through the write gate (ROADMAP-100 053). Returns whether it alerted."""
    m: dict[str, float] = json.loads(METRICS.read_text()) if METRICS.is_file() else {}
    recent: list[int] = json.loads(OUTCOMES.read_text()) if OUTCOMES.is_file() else []
    recent = [*recent, 1 if code else 0][-ALERT_WINDOW:]
    write_atomic(OUTCOMES, json.dumps(recent))
    failed, now = sum(recent), time.time()
    due = len(recent) >= ALERT_WINDOW // 2 and failed / len(recent) > ALERT_RATIO
    alerted = due and now - float(m.get("alerted_at") or 0) >= ALERT_EVERY
    if alerted:
        m["alerted_at"] = now
    write_atomic(METRICS, json.dumps(m, indent=2, sort_keys=True))
    if alerted:
        msg = ChatMessage(
            to="#debugassist-ops",
            title=f"GitHub App: {failed} of the last {len(recent)} runs failed",
            text="Read the failed runs' errors (`debugassist audit`, `.data/logs/app.jsonl`), fix the cause, then "
            "`debugassist app rerun GHA:owner/repo#n`.",
            level="alert",
        )
        gate.gated("chat.message", lambda: (chat or build_chat(get_settings())).send(msg), run_id=None,
                   detail={"to": msg.to, "title": msg.title})  # fmt: skip
        logs.event("app", "alert", failed=failed, window=len(recent))
    return alerted


class _User(BaseModel):
    login: str = ""
    type: str = "User"


class _Comment(BaseModel):
    body: str = ""
    author_association: str = ""
    user: _User = _User()


class _Issue(BaseModel):
    number: int = 0
    pull_request: Any = None  # present only when the issue is a pull request


class _Repo(BaseModel):
    full_name: str = ""


class IssueCommentEvent(BaseModel):
    """The parts of GitHub's `issue_comment` webhook payload a review request needs."""

    action: str = ""
    issue: _Issue = _Issue()
    comment: _Comment = _Comment()
    repository: _Repo = _Repo()


class ReviewRequest(BaseModel):
    repo: str
    pr: int
    instruction: str
    by: str = ""


def review_request(payload: Any) -> ReviewRequest | None:
    """An `@debugassist <instruction>` comment on one of the app's PRs from someone the repository trusts, as a
    queue item (ROADMAP-100 073); None for every other comment."""
    e = IssueCommentEvent.model_validate(payload)
    body = e.comment.body.strip()
    if e.action != "created" or e.issue.pull_request is None or not body.lower().startswith("@debugassist"):
        return None
    if e.comment.author_association not in TRUSTED or e.comment.user.type == "Bot":
        return None
    instruction = body[len("@debugassist") :].strip(" :,\n")
    if not instruction:
        return None
    return ReviewRequest(
        repo=e.repository.full_name, pr=e.issue.number, instruction=instruction[:500], by=e.comment.user.login
    )


class _CheckSuite(BaseModel):
    head_branch: str | None = None


class _CheckRunPayload(BaseModel):
    id: int = 0
    conclusion: str | None = None
    check_suite: _CheckSuite = _CheckSuite()


class _RepoPayload(BaseModel):
    full_name: str = ""
    default_branch: str = "main"


class CheckRunEvent(BaseModel):
    action: str = ""
    check_run: _CheckRunPayload = _CheckRunPayload()
    repository: _RepoPayload = _RepoPayload()


def ci_failure(payload: Any) -> str | None:
    """A `check_run` webhook for a failed check on the repository's default branch, as a `GHCI:` reference
    (ROADMAP-100 074); None for anything else (other branches, PRs, passing or cancelled checks)."""
    e = CheckRunEvent.model_validate(payload)
    if e.action != "completed" or e.check_run.conclusion not in FAILED_CHECK or not e.check_run.id:
        return None
    if e.check_run.check_suite.head_branch != e.repository.default_branch:
        return None
    return app_intake.ci_ref(e.repository.full_name, e.check_run.id)


def ci_pass(gate: PolicyGate, llm: str = "live", dry: bool = False) -> list[str]:
    """Run each queued CI failure once (a run per failed check; the poll remembers it in seen.json)."""
    done: list[str] = []
    for f in sorted(CI_QUEUE.glob("*.json")) if CI_QUEUE.is_dir() else []:
        ref = str(json.loads(f.read_text())["ref"])
        repo, _ = app_intake.parse_ci_ref(ref)
        if not gate.allowed_repo(repo):
            done.append(f"{ref}: not allowed by writes.yaml")
        elif ref in _seen():
            done.append(f"{ref}: already run")
        elif dry:
            done.append(f"would run {ref}")
            continue
        else:
            _mark(ref, {"result": "running", "at": time.time(), "attempts": 1})
            code = _spawn(ref, llm)
            _mark(ref, {"result": "done" if code == 0 else f"exit {code}", "at": time.time(), "attempts": 1})
            count(ci_runs=1, runs_failed=1 if code else 0)
            done.append(f"{ref}: {'done' if code == 0 else f'exit {code}'}")
        f.unlink()
    return done


def run_for_pr(repo: str, pr: int, runs: Path | None = None) -> str | None:
    """The newest run that opened this PR."""
    root = runs or RUNS_DIR
    for d in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True) if root.is_dir() else []:
        try:
            s = RunRef.model_validate_json((d / "state.json").read_text())
        except (OSError, ValueError):
            continue
        if s.pr is not None and s.pr.number == pr and s.issue is not None and s.issue.gh_repo == repo:
            return d.name
    return None


class _PRRef(BaseModel):
    number: int = 0


class _IssueRefState(BaseModel):
    gh_repo: str = ""


class RunRef(BaseModel):
    """Just enough of a run's state to find the run that opened a PR, without validating the whole state."""

    pr: _PRRef | None = None
    issue: _IssueRefState | None = None


def _spawn_fix(run_id: str, instruction: str) -> int:
    return subprocess.run(
        [str(CLI), "fix-diff", run_id, instruction], env=os.environ.copy(), check=False
    ).returncode


def review_pass(gate: PolicyGate, dry: bool = False) -> list[str]:
    """Hand each queued review request to the diff fixer (which re-validates, pushes and comments through the
    gate); returns what it did."""
    done: list[str] = []
    for f in sorted(REVIEWS.glob("*.json")) if REVIEWS.is_dir() else []:
        r = ReviewRequest.model_validate_json(f.read_text())
        repo, pr = r.repo, r.pr
        run = run_for_pr(repo, pr) if gate.allowed_repo(repo) else None
        if run is None:
            done.append(f"{repo}#{pr}: no run of this app opened it")
        elif dry:
            done.append(f"{repo}#{pr}: would revise run {run}")
            continue
        else:
            code = _spawn_fix(run, r.instruction)
            count(reviews=1, review_errors=1 if code else 0)
            logs.event("app", "review", pr=f"{repo}#{pr}", run=run, by=r.by, exit_code=code)
            done.append(f"{repo}#{pr}: revised by run {run} (exit {code})")
        f.unlink()
    return done


def poll_lock() -> IO[str] | None:
    """An exclusive lock on LOCK, or None when another poller holds it: two pollers would run every issue twice."""
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    f = LOCK.open("w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        return None
    return f


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


def _comment(a: GitHubApp, gate: PolicyGate, repo: str, number: int, kind: str, body: str) -> None:
    """The poller's own comments (not onboarded, failed) go through the write gate like the pipeline's."""
    gate.gated(
        "github.comment",
        lambda: a.comment(repo, number, body),
        run_id=None,
        detail={"repo": repo, "issue": number, "kind": kind},
        repo=repo,
    )


def run_one(
    a: GitHubApp,
    repo: str,
    number: int,
    *,
    llm: str = "live",
    dry: bool = False,
    gate: PolicyGate | None = None,
) -> int:
    """One labeled issue through the pipeline (its own process); returns the exit code."""
    gate = gate or PolicyGate(installed=a.installed_repos)
    ref = app_intake.ref(repo, number)
    try:
        app_intake.ensure_checkout(a, repo)
    except app_intake.NotOnboarded as exc:
        if not any(c.lstrip().startswith(NOT_ONBOARDED) for c in a.comments(repo, number)):
            _comment(
                a,
                gate,
                repo,
                number,
                "not_onboarded",
                f"{NOT_ONBOARDED}\nDebugAssist can't run here yet: this repository has no "
                "`.DebugAssist/pipeline.yaml` saying how to build and test it. See "
                "https://github.com/IshaanNene/DebugAssist/blob/main/docs/github-app.md#onboarding-a-repository.",
            )
        _mark(ref, {"result": "not_onboarded", "why": str(exc)})
        count(not_onboarded=1)
        return 0
    if dry:
        typer.echo(f"would run {ref}")
        return 0
    attempts = int(_seen().get(ref, {}).get("attempts") or 0) + 1
    _mark(ref, {"result": "running", "at": time.time(), "attempts": attempts})
    count(runs_started=1, retries=1 if attempts > 1 else 0)
    code = _spawn(ref, llm)
    count(runs_done=1 if code == 0 else 0, runs_failed=1 if code else 0)
    record_outcome(code, gate)
    _mark(ref, {"result": "done" if code == 0 else f"exit {code}", "at": time.time(), "attempts": attempts})
    typer.echo(f"{ref}: {'done' if code == 0 else f'exit {code} (attempt {attempts} of {MAX_ATTEMPTS})'}")
    logs.event("app", "run", issue=ref, exit_code=code, attempt=attempts)
    if code and attempts >= MAX_ATTEMPTS:
        count(runs_given_up=1)
        _comment(
            a,
            gate,
            repo,
            number,
            "failed",
            f"{FAILED}\nDebugAssist could not finish an analysis of this issue ({attempts} attempts, last exit "
            f"code {code}). The maintainers of this DebugAssist installation can see the run logs; remove and "
            "re-add the label to try again.",
        )
    return code


def requeue(repo: str, number: int) -> Path:
    """Forget the poll's record of an issue and queue it as if a webhook had delivered it."""
    ref = app_intake.ref(repo, number)
    seen = _seen()
    if seen.pop(ref, None) is not None:
        write_atomic(SEEN, json.dumps(seen, indent=2))
    QUEUE.mkdir(parents=True, exist_ok=True)
    f = QUEUE / f"rerun-{repo.replace('/', '--')}-{number}.json"
    write_atomic(f, json.dumps({"repo": repo, "number": number}))
    return f


@app.command()
def rerun(ref: Annotated[str, typer.Argument(help="GHA:owner/repo#123")]) -> None:
    """Run an issue again on the next poll (clears what the poll remembers about it; the app's comment stays)."""
    repo, number = app_intake.parse_ref(ref)
    f = requeue(repo, number)
    typer.echo(f"queued {ref} ({f.name}); `debugassist app poll` runs it next")


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
    lock = poll_lock()  # held until the process exits
    if lock is None:
        raise typer.BadParameter(f"another `debugassist app poll` is running ({LOCK})")
    while True:
        marker = QUEUE.parent / REFRESH
        if (
            marker.exists()
        ):  # installed on, or removed from, a repository since the last pass (ROADMAP-100 072)
            marker.unlink(missing_ok=True)
            if (refresh := getattr(a, "refresh", None)) is not None:
                refresh()
            logs.event("app", "installations_refreshed")
        try:
            work = pending(a, gate, label)
        except RateLimited as exc:  # wait it out instead of hammering the API every interval
            typer.echo(str(exc), err=True)
            logs.event("app", "rate_limited", wait_s=exc.wait_s)
            count(rate_limited=1)
            if once:
                return
            time.sleep(min(exc.wait_s, MAX_RATE_WAIT) + 1)
            continue
        for line in [*review_pass(gate, dry=dry), *ci_pass(gate, llm=llm, dry=dry)]:
            typer.echo(line)
        for repo, number, why in work:
            typer.echo(f"{repo}#{number} ({why})")
            try:
                run_one(a, repo, number, llm=llm, dry=dry, gate=gate)
            except Exception as exc:  # one repository's API error must not stop the poll
                logs.event(
                    "app", "error", issue=f"{repo}#{number}", error=f"{type(exc).__name__}: {exc}"[:300]
                )
                count(errors=1)
                typer.echo(
                    f"{repo}#{number}: {type(exc).__name__}: {redact_secrets(str(exc))[:300]}", err=True
                )
            finally:
                if not dry:
                    done_delivery(repo, number)
        if once:
            return
        time.sleep(interval)
