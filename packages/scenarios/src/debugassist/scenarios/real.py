"""Real open-source bugs: a public GitHub issue run through the pipeline on the code it was filed against.

Each case has two halves, kept apart like the catalog's:
- the input, `sources/github/issues/<name>.yaml`: the issue as shown to the agent (symptom sections only when the
  original report names its own fix), the repo, and the commit it was filed against;
- the answer key, `groundtruth/real/<REAL-id>.yaml`: the upstream fix commit, the root-cause location, and the fix's
  own regression test as the hidden test.

`prepare` builds `targets/<repo>`: upstream cloned at the buggy commit with every later commit, branch and tag
removed (the fix must not be findable in history), plus one local commit adding `.DebugAssist/pipeline.yaml` — how a
team would onboard its repo — tagged `v<version>` for the sandbox. It refuses to finish if the fix is reachable.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from debugassist.core.policy import ROOT

ISSUES = ROOT / "sources" / "github" / "issues"
ANSWERS = ROOT / "groundtruth" / "real"
TARGETS = ROOT / "targets"


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Checkout(_M):
    url: str
    branch: str
    commit: str
    version: str
    config: str  # .DebugAssist/pipeline.yaml for the repo


class GitHubIssue(_M):
    """The pipeline's input for a real bug (no answers in here)."""

    id: str  # GH-<repo>-<number>
    case: str  # REAL-…
    url: str
    filed_at: str
    title: str
    repo: str
    gh_repo: str
    language: str
    component: str
    about: str  # one line on what the repository is, for the agents' prompts
    checkout: Checkout
    body: str
    withheld: str | None = None


class Location(_M):
    repo: str
    module: str | None = None
    file: str
    function: str | None = None


class HiddenTest(_M):
    src: str
    repo: str
    dest: str
    command: str | None = None  # how to run it in the repo's sandbox


class Truth(_M):
    location: Location
    rca_facts: list[str]
    hidden_tests: list[HiddenTest]
    fix: str | None = None  # a reference diff; the upstream fix commit is named in `upstream` instead


class RealCase(_M):
    """The answer key for one real bug."""

    id: str
    title: str
    source: str
    repo: str
    language: str
    component: str = "."
    category: Literal[
        "own_code", "third_party_lib", "infra", "network", "flag_config", "device_os", "not_a_bug"
    ]
    expected_outcome: Literal["pr", "rca_only", "route"]
    upstream: dict[str, str]
    ground_truth: Truth
    validation: dict[str, str]

    def path(self, rel: str) -> Path:
        return ANSWERS.parent / rel  # relative to groundtruth/, like the catalog's paths


@cache
def issues() -> dict[str, GitHubIssue]:
    out: dict[str, GitHubIssue] = {}
    for p in sorted(ISSUES.glob("*.yaml")):
        issue = GitHubIssue.model_validate(yaml.safe_load(p.read_text()))
        out[issue.id.upper()] = issue
    return out


def load_issue(ref: str) -> GitHubIssue:
    key = ref.upper()
    if key not in issues():
        raise KeyError(f"unknown GitHub issue {ref!r}; known: {sorted(issues())}")
    return issues()[key]


def load_case(case_id: str) -> RealCase:
    return RealCase.model_validate(yaml.safe_load((ANSWERS / f"{case_id.upper()}.yaml").read_text()))


def cases() -> list[str]:
    return sorted(p.stem for p in ANSWERS.glob("REAL-*.yaml"))


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=check)


def prepare(case_id: str, log: Callable[[str], None] = print) -> Path:
    """Build (or verify) targets/<repo> for a case; returns its path."""
    case = load_case(case_id)
    issue = load_issue(case.source)
    co = issue.checkout
    dest = TARGETS / issue.repo
    tag = f"v{co.version}"
    if not (dest / ".git").exists():
        log(f"cloning {co.url} ({co.branch}) into {dest.relative_to(ROOT)} …")
        subprocess.run(
            ["git", "clone", "-q", "--branch", co.branch, co.url, str(dest)], check=True, capture_output=True
        )
        _git(dest, "checkout", "-q", "-B", co.branch, co.commit)
        for ref in _git(dest, "for-each-ref", "--format=%(refname:short)", "refs/heads").stdout.split():
            if ref != co.branch:
                _git(dest, "branch", "-q", "-D", ref)
        _git(dest, "remote", "remove", "origin")
        for t in _git(dest, "tag").stdout.split():
            if _git(dest, "merge-base", "--is-ancestor", t, co.commit, check=False).returncode:
                _git(dest, "tag", "-d", t)
        cfg = dest / ".DebugAssist" / "pipeline.yaml"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(co.config)
        _git(dest, "add", ".DebugAssist/pipeline.yaml")
        _git(
            dest,
            "-c",
            "user.name=DebugAssist",
            "-c",
            "user.email=debugassist@localhost",
            "commit",
            "-q",
            "-m",
            "chore: add DebugAssist pipeline config",
        )
        _git(dest, "tag", tag)
        _git(dest, "reflog", "expire", "--expire=now", "--all")
        _git(dest, "gc", "-q", "--prune=now")
    fix = case.upstream.get("fix_commit", "")
    if fix and _git(dest, "cat-file", "-e", fix, check=False).returncode == 0:
        raise RuntimeError(
            f"{dest}: the fix commit {fix[:10]} is reachable — the checkout would leak the answer"
        )
    if _git(dest, "rev-parse", "-q", "--verify", f"refs/tags/{tag}", check=False).returncode:
        raise RuntimeError(f"{dest}: tag {tag} is missing")
    return dest
