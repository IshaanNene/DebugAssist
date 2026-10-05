"""Bridge from pipeline nodes to the harness: the agent type's skills for a node (names + descriptions in
the prompt, bodies through `load_skill`), plus the owning domain's knowledge base, from the marketplace at
the agent type's pinned ref."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool

from debugassist.harness import domains, marketplace
from debugassist.harness import skills as harness_skills
from debugassist.pipeline.state import Issue


def root_for(agent_type: dict[str, Any]) -> Path:
    return marketplace.fetch(marketplace.ref_for(str(agent_type.get("marketplace_ref", "working"))))


def for_node(agent_type: dict[str, Any], node: str, issue: Issue | None = None) -> tuple[str, list[BaseTool]]:
    """(prompt section, tools) for one LLM node."""
    root = root_for(agent_type)
    by_node: dict[str, list[str]] = agent_type.get("skills") or {}
    names = list(by_node.get(node) or [])
    docs = domains.knowledge(root, domains.for_issue(root, issue.repo, issue.component)) if issue else {}
    if not names and not docs:
        return "", []
    budget = int(agent_type.get("skill_token_budget", 6000))
    return (
        harness_skills.catalog(names, root, docs),
        [harness_skills.load_skill_tool(names, root, budget, docs)],
    )


def find(name: str) -> Path | None:
    """A skill's file in this checkout (proposals edit the working tree, not a pinned copy)."""
    return marketplace.find(name)
