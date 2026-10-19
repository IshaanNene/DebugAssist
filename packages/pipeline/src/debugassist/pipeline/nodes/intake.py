"""N0 ingest: the issue from Vitals, BugDrop, a frozen or a live GitHub issue."""

from __future__ import annotations

from typing import Any

import httpx
import yaml

from debugassist.core.policy import ROOT
from debugassist.pipeline import (
    app_intake,
    collector,
)
from debugassist.pipeline.deps import APPS, Deps
from debugassist.pipeline.state import (
    Issue,
    RunState,
)


async def ingest(state: RunState, deps: Deps) -> dict[str, Any]:
    ref = state.issue_ref
    if ref.upper().startswith("BD-"):
        return with_agent_type(await collector.ingest_bugdrop(ref, deps), deps)
    if ref.upper().startswith("GH-"):
        return with_agent_type(collector.ingest_github(ref), deps)
    if ref.upper().startswith("GHA:"):
        if deps.app is None:
            raise ValueError("a GitHub App issue needs the app configured (docs/github-app.md)")
        return with_agent_type(app_intake.ingest(ref, deps.app), deps)
    if ref.upper().startswith("GHCI:"):
        if deps.app is None:
            raise ValueError("a CI failure needs the GitHub App configured (docs/github-app.md)")
        return with_agent_type(app_intake.ingest_ci(ref, deps.app), deps)
    if not ref.upper().startswith("VIT-"):
        raise ValueError(
            f"unknown issue reference {ref!r}: expected a Vitals issue (VIT-…), a BugDrop report (BD-…) "
            "a frozen GitHub issue (GH-…), a GitHub App issue (GHA:owner/repo#123) or a CI failure (GHCI:owner/repo@id)"
        )
    async with httpx.AsyncClient(base_url=deps.vitals_url, timeout=15) as http:
        d = (await http.get(f"/api/issues/{ref.upper()}")).raise_for_status().json()
    g = d["group"]
    ev: dict[str, Any] = d.get("latest_event") or {}
    repo, gh_repo, component, language = APPS[d["app"]]
    issue = Issue(
        source="vitals",
        id=d["id"],
        url=f"{deps.vitals_ui}/issues/{d['id']}",
        title=d["title"],
        kind=d["kind"],
        app=d["app"],
        platform=g["platform"],
        version=ev.get("version", g["last_version"]),
        first_version=g["first_version"],
        last_version=g["last_version"],
        fingerprint=d["fingerprint"],
        events=g["count"],
        culprit=g.get("culprit"),
        repo=repo,
        gh_repo=gh_repo,
        component=component,
        language=language,
        latest_event=ev,
        session_id=ev.get("session_id"),
        opened_at=d.get("opened_at"),
    )
    return with_agent_type(issue, deps)


def with_agent_type(issue: Issue, deps: Deps) -> dict[str, Any]:
    """Resolve the agent type for this issue (harness): --agent-type, else the most specific matching type,
    else the target repo's default_agent_type (its .DebugAssist/pipeline.yaml)."""
    from debugassist.harness import agent_types

    pipeline = ROOT / "targets" / issue.repo / ".DebugAssist" / "pipeline.yaml"
    repo_default = (
        yaml.safe_load(pipeline.read_text()).get("default_agent_type") if pipeline.is_file() else None
    )
    t, why = agent_types.resolve(
        source=issue.source,
        kind=issue.kind,
        repo=issue.repo,
        language=issue.language,
        repo_default=repo_default,
        override=deps.extra.get("agent_type"),
    )
    deps.agent_type = t.model_dump()
    return {"issue": issue, "agent_type": t.name, "agent_type_reason": why}
