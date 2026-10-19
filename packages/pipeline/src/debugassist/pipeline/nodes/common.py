"""Helpers every node uses: prompts, the run's sandbox and component config, LLM bookkeeping, the proof rules."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from debugassist.core import hostgit
from debugassist.core.evidence import EvidenceItem
from debugassist.core.policy import ROOT
from debugassist.core.settings import Integration, Mode
from debugassist.integrations.sandbox import CommandResult, Sandbox
from debugassist.llm.runner import is_daily_quota
from debugassist.llm.spec import LLMResult
from debugassist.llm.workspace_tools import is_test_path
from debugassist.pipeline import (
    crossrepo,
    proof,
    release,
)
from debugassist.pipeline.deps import Deps
from debugassist.pipeline.state import (
    Issue,
    RunState,
)

PROMPTS = Path(__file__).parents[1] / "prompts"


PRIORITIES = ["P4", "P3", "P2", "P1", "P0"]


NON_ACTIONABLE = {"route_rca", "close_rca"}


def load_prompt(name: str) -> str:
    return (PROMPTS / name).read_text()


def llm_summary(r: LLMResult) -> dict[str, Any]:
    return {
        "status": r.status,
        "mode": r.mode,
        "model": r.model,
        "turns": r.turns,
        "cost_usd": r.cost_usd,
        "input_tokens": r.input_tokens,
        "output_tokens": r.output_tokens,
        "error": r.error,
        "wall_ms": r.wall_ms,
        "tool_calls": [c.model_dump() for c in r.tool_calls],
    }


def sandbox_for(state: RunState) -> Sandbox:
    assert state.issue
    return Sandbox(
        state.run_id, ROOT / "targets" / state.issue.repo, state.issue.gh_repo, state.issue.language
    )


def run_values(state: RunState) -> dict[str, str]:
    """The run's values for in-process code tools (`core.runctx`), set around every node by the graph."""
    values = {"DEBUGASSIST_RUN_ID": state.run_id, "DEBUGASSIST_MODE": state.mode}
    if state.issue:
        sb = sandbox_for(state)
        values["CODE_REPOS"] = json.dumps(crossrepo.code_repos(state.run_id, state.issue, sb.worktree))
    return values


def code_repos_env(state: RunState) -> dict[str, str]:
    assert state.issue
    sb = sandbox_for(state)
    # Service URLs for the MCP servers: localhost by default; service names inside a runtime container.
    passthrough = (
        "LOKI_URL",
        "JAEGER_URL",
        "PROMETHEUS_URL",
        "BUGDROP_URL",
        "INCIDENTS_URL",
        "DEBUGASSIST_ROOT",
        "DA_CONTEXT",
    )
    env = {
        "VITALS_URL": os.environ.get("VITALS_URL", "http://localhost:8100"),
        "UNLEASH_URL": os.environ.get("UNLEASH_URL", "http://localhost:4242"),
        **{k: os.environ[k] for k in passthrough if k in os.environ},
        "CODE_REPOS": json.dumps(crossrepo.code_repos(state.run_id, state.issue, sb.worktree)),
        "DEBUGASSIST_RUN_ID": state.run_id,
        "DEBUGASSIST_MODE": state.mode,
        "PATH": os.environ.get("PATH", ""),
    }
    return env


def top_in_app(frames: list[dict[str, Any]]) -> dict[str, Any] | None:
    in_app = [f for f in frames if f.get("in_app", True) and "vendor/" not in str(f.get("file"))]
    return in_app[-1] if in_app else (frames[-1] if frames else None)


def pipeline_yaml(worktree: Path, issue: Issue | None = None) -> dict[str, Any]:
    """How to build and test the repository, as of the release under test — never the agent's copy.

    The fix agent may edit any file in its worktree, `.DebugAssist/pipeline.yaml` included; read from there, a
    `test: "true"` would make "the suite passes" mean nothing (audit P2-8)."""
    if issue is not None:
        shown = hostgit.run(worktree, "show", f"v{issue.last_version}:.DebugAssist/pipeline.yaml")
        if shown.returncode == 0:
            return yaml.safe_load(shown.stdout)
        if hostgit.run(worktree, "rev-parse", "--verify", "-q", f"v{issue.last_version}").returncode == 0:
            raise RuntimeError(f"v{issue.last_version} has no .DebugAssist/pipeline.yaml")
    return yaml.safe_load((worktree / ".DebugAssist" / "pipeline.yaml").read_text())


def static_problem(sb: Sandbox, comp: dict[str, Any], workdir: str) -> str | None:
    """The repository's own CI checks (lint + typecheck) must pass too: a fix CI rejects is not a fix."""
    if not comp.get("lint"):
        return None
    res = sb.run(str(comp["lint"]), workdir=workdir)
    return None if res.exit_code == 0 else f"`{comp['lint']}` (run by CI) fails:\n{res.output[-1200:]}"


def stop_if_out_of_quota(r: LLMResult, state: RunState, node: str) -> None:
    """An exhausted daily LLM quota is an infrastructure failure, not a failed fix attempt: stop the run
    (no retries, no ship, no writes) so it can be resumed after the reset."""
    if r.status == "error" and is_daily_quota(r.error):
        raise RuntimeError(
            f"LLM provider's daily quota is exhausted ({(r.error or '')[:160]}). Resume after the reset: "
            f"debugassist run {state.issue_ref} --resume {state.run_id} --from-node {node}"
        )


# The reproduction rules live in `proof.py`; the names nodes has always used stay importable from here.
ASSERTION_FAILED = proof.ASSERTION_FAILED


TIMEOUT_MARKERS = proof.TIMEOUT_MARKERS


error_signature = proof.error_signature


wrong_value_report = proof.wrong_value_report


error_type = proof.error_type


error_pattern = proof.error_pattern


repro_problem = proof.repro_problem


def run_on_release(sb: Sandbox, base: str, run: Callable[[Sandbox], CommandResult]) -> CommandResult | None:
    """Run in a disposable checkout of the release with the worktree's tests but not its source change (P3-16:
    the worktree, and the fix in it, is never touched). Against the release, not HEAD: once a fix is committed
    (diff fixer, a resumed run), HEAD already contains it. None if there is no source change."""
    changed = release.changes(sb.worktree, base)
    if all(is_test_path(p) for p in changed):
        return None
    with release.release_checkout(sb, base, [p for p in changed if is_test_path(p)]) as rsb:
        return run(rsb)


def component_cfg(state: RunState, worktree: Path) -> dict[str, Any]:
    assert state.issue
    cfg = pipeline_yaml(worktree, state.issue)["components"]
    if state.issue.component == ".":
        return next(iter(cfg.values()))
    return cfg[state.issue.component]


def source_label(issue: Issue) -> str:
    return {"bugdrop": "BugDrop report", "github": "GitHub issue"}.get(issue.source, "Vitals issue")


def bot_branch(issue: Issue, deps: Deps) -> str:
    branch = (
        f"debugassist/{issue.id.lower()}-{re.sub(r'[^a-z0-9]+', '-', issue.title.lower())[:40].strip('-')}"
    )
    if deps.settings.mode(Integration.GITHUB) is not Mode.LIVE:
        branch += "-mock"  # never collide with (and clean up) a live run's worktree for the real PR branch
    return branch


def evidence_bundle(items: list[EvidenceItem], budget_chars: int = 40_000) -> str:
    parts: list[str] = []
    used = 0
    for it in items:
        body = json.dumps(it.data, default=str)
        chunk = f"### {it.id} — {it.summary}\n{body[:9000]}\n"
        if used + len(chunk) > budget_chars:
            parts.append(
                f"### {it.id} — {it.summary}\n(omitted for length; call the matching tool for details)\n"
            )
            continue
        parts.append(chunk)
        used += len(chunk)
    return "\n".join(parts)
