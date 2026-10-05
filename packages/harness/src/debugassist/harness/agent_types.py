"""Agent types (SPEC §7): one fixed plan, many configurations. A type sets, per LLM node, the model limits,
MCP servers and skills; which subagents D7 may pick; the validation ladder; the runtime image; and which
marketplace ref its skills come from. The harness resolves a type per issue."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from debugassist.core.policy import ROOT

AGENT_TYPES = ROOT / "configs" / "agent_types"
DEFAULT = "web-crash"


class Match(BaseModel):
    """When a type applies; every listed field must match (empty = any)."""

    model_config = ConfigDict(extra="forbid")
    sources: list[str] = Field(default_factory=list[str])  # vitals | bugdrop
    kinds: list[str] = Field(default_factory=list[str])  # crash | perf | bug_report | error
    repos: list[str] = Field(default_factory=list[str])
    languages: list[str] = Field(default_factory=list[str])


class Subagents(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allow: list[str] = Field(default_factory=list[str])  # empty = every subagent in configs/subagents.yaml
    prefer: list[str] = Field(default_factory=list[str])  # listed first to D7


class Validation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_attempts: int = 3
    ladder: list[str] = Field(default_factory=lambda: ["unit", "integration", "e2e_env"])


class AgentType(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str
    priority: int = 0  # higher wins when several types match
    match: Match = Field(default_factory=Match)
    marketplace_ref: str = "working"  # "working" (this checkout) or a git ref; DA_MARKETPLACE_REF overrides
    skill_token_budget: int = 6000  # skills loaded into one node, in tokens (≈ chars / 4)
    nodes: dict[str, dict[str, Any]]
    skills: dict[str, list[str]] = Field(default_factory=dict[str, list[str]])
    subagents: Subagents = Field(default_factory=Subagents)
    validation: Validation = Field(default_factory=Validation)
    runtime_image: str
    run_budget_usd: float = 3.0

    def matches(
        self, *, source: str | None, kind: str | None, repo: str | None, language: str | None
    ) -> bool:
        m = self.match
        checks = [(m.sources, source), (m.kinds, kind), (m.repos, repo), (m.languages, language)]
        return any(m.model_dump().values()) and all(
            not allowed or value in allowed for allowed, value in checks
        )


def load(name: str, directory: Path = AGENT_TYPES) -> AgentType:
    path = directory / f"{name}.yaml"
    if not path.is_file():
        known = ", ".join(sorted(p.stem for p in directory.glob("*.yaml")))
        raise ValueError(f"unknown agent type {name!r} (known: {known})")
    return AgentType.model_validate(yaml.safe_load(path.read_text()))


def all_types(directory: Path = AGENT_TYPES) -> dict[str, AgentType]:
    return {p.stem: load(p.stem, directory) for p in sorted(directory.glob("*.yaml"))}


def resolve(
    *,
    source: str | None,
    kind: str | None,
    repo: str | None,
    language: str | None,
    repo_default: str | None = None,
    override: str | None = None,
    directory: Path = AGENT_TYPES,
) -> tuple[AgentType, str]:
    """(type, why): an explicit override, else the most specific matching type, else the target repo's
    `default_agent_type` (its .DebugAssist/pipeline.yaml), else web-crash."""
    if override:
        return load(override, directory), "requested (--agent-type)"
    types = all_types(directory)
    hits = [t for t in types.values() if t.matches(source=source, kind=kind, repo=repo, language=language)]
    if hits:
        best = max(hits, key=lambda t: t.priority)
        return best, f"matched {best.match.model_dump(exclude_defaults=True)}"
    if repo_default and repo_default in types:
        return types[repo_default], f"default for {repo}"
    return types[DEFAULT], "fallback"
