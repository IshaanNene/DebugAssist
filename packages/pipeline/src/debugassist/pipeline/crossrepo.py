"""Cross-repo investigation and hand-off (ROADMAP P14).

A rider's report or a client crash shows where a bug is *seen*; the defect may live in a service. The RCA agent
and its subagents therefore get read-only worktrees of the other target repos (at what is deployed), and when the
root cause lands in another repo the fix stage is handed off there: a fresh sandbox in that repo at its deployed
release, that repo's component and toolchain, and its default agent type. The plan stays fixed — this only
changes *where* the fix steps run, from a deterministic check of the RCA's location.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import yaml

from debugassist.core.policy import ROOT
from debugassist.integrations.sandbox import RUNS, Sandbox
from debugassist.pipeline.deps import APPS, Deps
from debugassist.pipeline.state import Issue, RunState

TARGETS: dict[str, str] = {repo: gh for repo, gh, _, _ in APPS.values()}  # repo name → owner/name


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def deployed_version(repo_path: Path) -> str | None:
    """The release checked out (what the stack runs): the tag at HEAD, else the latest tag behind it."""
    for args in (("describe", "--tags", "--exact-match", "HEAD"), ("describe", "--tags", "--abbrev=0")):
        p = _git(repo_path, *args)
        if p.returncode == 0 and p.stdout.strip():
            return p.stdout.strip().removeprefix("v")
    return None


def peer_roots(run_id: str, current: str) -> dict[str, Path]:
    """Read-only worktrees of every other target repo at its deployed HEAD, created once per run."""
    out: dict[str, Path] = {}
    for repo in TARGETS:
        if repo == current:
            continue
        src = ROOT / "targets" / repo
        dest = RUNS / run_id / "peers" / repo
        if not dest.exists():
            if not (src / ".git").exists():
                continue  # not checked out here (e.g. a private submodule in CI)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if _git(src, "worktree", "add", "--detach", "-q", str(dest), "HEAD").returncode:
                continue
        out[repo] = dest
    return out


def code_repos(run_id: str, issue: Issue, worktree: Path) -> dict[str, str]:
    """CODE_REPOS for the MCP servers: the issue's sandbox plus read-only peers."""
    return {issue.repo: str(worktree), **{k: str(v) for k, v in peer_roots(run_id, issue.repo).items()}}


def plan_handoff(issue: Issue, repo: str, file: str, repo_root: Path) -> dict[str, str] | None:
    """Where the fix should run when the root cause is in `repo`/`file`, or None to stay. Pure: reads only
    the target's `.DebugAssist/pipeline.yaml` and checks that the file exists there."""
    repo = repo.split("/")[-1]
    if repo == issue.repo or repo not in TARGETS:
        return None
    rel = file.strip().lstrip("./")
    if not rel or not (repo_root / rel).is_file():
        return None  # never hand off on a path that does not exist (a guess, not a finding)
    cfg: dict[str, Any] = yaml.safe_load((repo_root / ".DebugAssist" / "pipeline.yaml").read_text())
    components: dict[str, dict[str, Any]] = cfg.get("components") or {}
    match: tuple[str, str] | None = None  # (component, language)
    root: tuple[str, str] | None = None  # a component at the repo root (the client)
    for name, c in components.items():
        path = str(c.get("path", name)).strip("/")
        if path in ("", "."):
            root = (".", str(c.get("language", "")))
        elif rel.startswith(path + "/"):
            match = (name, str(c.get("language", "")))
            break
    chosen = match or root
    if not chosen or not chosen[1]:
        return None
    component, language = chosen
    return {
        "repo": repo,
        "gh_repo": TARGETS[repo],
        "component": component,
        "language": language,
        "default_agent_type": str(cfg.get("default_agent_type") or ""),
    }


def retarget(state: RunState, deps: Deps, branch: str) -> dict[str, Any] | None:
    """After RCA: if the root cause is in another target repo, move the fix sandbox there. Returns the
    RunState update, or None when the fix stays in the issue's repo."""
    issue, rca = state.issue, state.rca
    if not issue or not rca or not rca.output:
        return None
    loc = rca.output.location
    peers = peer_roots(state.run_id, issue.repo)
    root = peers.get(loc.repo.split("/")[-1])
    plan = plan_handoff(issue, loc.repo, loc.file, root) if root else None
    if not plan:
        return None
    version = deployed_version(ROOT / "targets" / plan["repo"])
    if not version:
        return None
    Sandbox(state.run_id, ROOT / "targets" / issue.repo, issue.gh_repo, issue.language).destroy()
    new = issue.model_copy(
        update={k: plan[k] for k in ("repo", "gh_repo", "component", "language")} | {"last_version": version}
    )
    Sandbox(state.run_id, ROOT / "targets" / new.repo, new.gh_repo, new.language).create(
        f"v{version}", branch
    )
    update: dict[str, Any] = {
        "issue": new,
        "handoff": {
            "from": {"repo": issue.repo, "component": issue.component, "version": issue.last_version},
            "to": {"repo": new.repo, "component": new.component, "version": version},
            "reason": f"root cause in {new.repo}/{loc.file} → {loc.function}",
        },
    }
    if plan["default_agent_type"] and plan["default_agent_type"] != state.agent_type:
        update["agent_type"] = plan["default_agent_type"]
        update["agent_type_reason"] = f"handed off to {new.repo}/{new.component}"
    return update
