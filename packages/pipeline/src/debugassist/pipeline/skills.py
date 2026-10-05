"""Markdown skills from the marketplace (marketplace/plugins/*/skills/<name>/SKILL.md), loaded into an LLM
node's system prompt as the agent type lists them (`skills: {node: [names]}`)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from debugassist.core.policy import ROOT

MARKETPLACE = ROOT / "marketplace"


def find(name: str, root: Path = MARKETPLACE) -> Path | None:
    hits = sorted(root.glob(f"plugins/*/skills/{name}/SKILL.md"))
    return hits[0] if hits else None


def body(path: Path) -> str:
    text = path.read_text()
    if text.startswith("---"):
        text = text.split("---", 2)[2]
    return text.strip()


def for_node(agent_type: dict[str, Any], node: str, root: Path = MARKETPLACE) -> str:
    by_node: dict[str, list[str]] = agent_type.get("skills") or {}
    names = by_node.get(node) or []
    parts = [f"## Skill: {n}\n\n{body(p)}" for n in names if (p := find(n, root))]
    return ("\n\n# Skills\n\n" + "\n\n".join(parts)) if parts else ""
