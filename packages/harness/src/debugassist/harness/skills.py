"""Skill loading for our agent runner with progressive disclosure (PLAN A4).

The system prompt lists each available skill by name and description only; the agent calls
`load_skill(name)` to read one when it is relevant. Bodies count against the node's token budget, so a
node cannot pull the whole marketplace into its context.
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import BaseTool, tool

from debugassist.harness import marketplace
from debugassist.harness.domains import Doc


def _available(root: Path, docs: dict[str, Doc] | None) -> dict[str, tuple[str, str]]:
    """name → (description, body) for skills and domain knowledge-base docs."""
    out = {n: (s.description, s.body) for n, s in marketplace.skills(root).items()}
    out.update({n: (d.description, d.body) for n, d in (docs or {}).items()})
    return out


def catalog(names: list[str], root: Path, docs: dict[str, Doc] | None = None) -> str:
    """The prompt section: available skills (name: description) and how to load them."""
    available = _available(root, docs)
    names = [*names, *(docs or {})]
    rows = [f"- {n}: {available[n][0]}" for n in names if n in available]
    if not rows:
        return ""
    return (
        "\n\n# Skills\n\nYou can load these skills (team know-how for this kind of fix) with the load_skill "
        "tool (kb/… entries are the owning domain's knowledge base). Load the ones that apply before you act:\n"
        + "\n".join(rows)
    )


def load_skill_tool(
    names: list[str], root: Path, budget_tokens: int, docs: dict[str, Doc] | None = None
) -> BaseTool:
    available = _available(root, docs)
    names = [*names, *(docs or {})]
    used: dict[str, int] = {}

    @tool
    def load_skill(name: str) -> str:
        """Read one of the skills listed in your instructions (by its exact name)."""
        if name not in names or name not in available:
            return f"unknown skill {name!r}; available: {', '.join(n for n in names if n in available)}"
        if name in used:
            return f"{name} is already loaded above."
        body = available[name][1]
        tokens = len(body) // 4
        if sum(used.values()) + tokens > budget_tokens:
            return f"cannot load {name}: the skill budget for this step ({budget_tokens} tokens) is used up"
        used[name] = tokens
        return f"# Skill: {name}\n\n{body}"

    return load_skill
