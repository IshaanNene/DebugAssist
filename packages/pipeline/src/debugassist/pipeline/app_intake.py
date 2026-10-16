"""Live GitHub issues through the GitHub App: `GHA:owner/repo#123`.

A repository the app is installed on is checked out into `targets/gh--<owner>--<repo>` (gitignored) at its
default branch's head, which is tagged locally as the release under test (`vapp-<sha>`); the fix branches from
there and the draft PR targets the default branch. The repository opts in by carrying `.DebugAssist/pipeline.yaml`
(how to build and test it, as for the real-bug cases); without it nothing runs. The clone URL holds the
installation token goes to git through its environment (`http.extraheader`), never in a URL, argv or `.git/config`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import yaml

from debugassist.core import hostgit
from debugassist.core.policy import ROOT
from debugassist.core.redaction import redact_secrets
from debugassist.integrations.github_app import GitHubApp
from debugassist.pipeline.state import Issue

TARGETS = ROOT / "targets"
_REF = re.compile(r"^GHA:([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)$", re.I)


class NotOnboarded(RuntimeError):
    """The repository has no .DebugAssist/pipeline.yaml."""


def parse_ref(ref: str) -> tuple[str, int]:
    m = _REF.match(ref.strip())
    if not m:
        raise ValueError(f"not a GitHub App issue reference: {ref!r} (expected GHA:owner/repo#123)")
    return m.group(1), int(m.group(2))


def ref(repo: str, number: int) -> str:
    return f"GHA:{repo}#{number}"


def target_name(repo: str) -> str:
    return "gh--" + repo.replace("/", "--")


def _git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    out = hostgit.run(cwd, *args, extra_env=env)
    if out.returncode:
        raise RuntimeError(redact_secrets(f"git {args[0]} failed: {out.stderr.strip()[-300:]}"))
    return out.stdout.strip()


def ensure_checkout(app: GitHubApp, repo: str) -> tuple[Path, str, str, dict[str, Any]]:
    """(checkout, short sha, default branch, the repo's pipeline config) at the default branch's head."""
    info = app.repo_info(repo)
    branch = str(info.get("default_branch") or "main")
    dest = TARGETS / target_name(repo)
    url, auth = app.clone_url(repo), app.git_env(repo)
    if not (dest / ".git").exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        _git(dest.parent, "clone", "-q", "--branch", branch, url, str(dest), env=auth)
    else:
        _git(dest, "fetch", "-q", url, branch, env=auth)
        _git(dest, "checkout", "-q", "-f", "-B", branch, "FETCH_HEAD")
    sha = _git(dest, "rev-parse", "--short=10", "HEAD")
    cfg_file = dest / ".DebugAssist" / "pipeline.yaml"
    if not cfg_file.is_file():
        raise NotOnboarded(f"{repo} has no .DebugAssist/pipeline.yaml on {branch}; see docs/github-app.md")
    _git(dest, "tag", "-f", f"vapp-{sha}")
    return dest, sha, branch, cast(dict[str, Any], yaml.safe_load(cfg_file.read_text()) or {})


def ingest(ref_: str, app: GitHubApp) -> Issue:
    repo, number = parse_ref(ref_)
    gh = app.issue(repo, number)
    _, sha, branch, cfg = ensure_checkout(app, repo)
    comps = cast(dict[str, dict[str, Any]], cfg.get("components") or {})
    component = "." if "." in comps else next(iter(comps), ".")
    language = str((comps.get(component) or {}).get("language") or "python")
    info = app.repo_info(repo)
    about = str(info.get("description") or "").strip()
    version = f"app-{sha}"
    return Issue(
        source="github",
        id=f"GHA-{repo.replace('/', '-')}-{number}",
        url=gh.url,
        title=gh.title[:160],
        kind="bug_report",
        app=repo.split("/")[1],
        platform="repository",
        version=version,
        first_version=version,
        last_version=version,
        events=1,
        repo=target_name(repo),
        gh_repo=repo,
        component=component,
        language=language,
        opened_at=gh.created_at,
        report={"title": gh.title, "body": gh.body, "url": gh.url, "filed_at": gh.created_at},
        about=f"{repo}{f', {about}' if about else ''} (the default branch, {branch}, at {sha})",
        base_branch=branch,
        app_issue=number,
    )
