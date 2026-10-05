"""Domain extensions (SPEC §1.5, §7): the platform team owns the harness; domain owners plug in their own
subagents and knowledge base without touching it.

    marketplace/domains/<domain>/domain.yaml   name, owners, components, subagents (subagents.yaml format)
    marketplace/domains/<domain>/kb/*.md       knowledge base docs (frontmatter: description)

A domain applies to an issue when the issue's repo/component is one of its components. Its subagents join
the pool D7 chooses from; its knowledge-base docs become loadable next to the node's skills.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from debugassist.harness import marketplace


class Component(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repo: str
    path: str = "."


class Domain(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str
    owners: list[str]
    components: list[Component]
    subagents: dict[str, dict[str, Any]] = Field(default_factory=dict[str, dict[str, Any]])


@dataclass(frozen=True)
class Doc:
    name: str  # kb/<domain>/<file stem>
    description: str
    body: str


def load_all(root: Path) -> dict[str, Domain]:
    out: dict[str, Domain] = {}
    for f in sorted(root.glob("domains/*/domain.yaml")):
        d = Domain.model_validate(yaml.safe_load(f.read_text()))
        out[d.name] = d
    return out


def for_issue(root: Path, repo: str | None, component: str | None) -> list[Domain]:
    comp = (component or ".").strip("/") or "."
    return [
        d
        for d in load_all(root).values()
        if any(c.repo == repo and c.path.strip("/") in (comp, ".") for c in d.components)
    ]


def knowledge(root: Path, domains: list[Domain]) -> dict[str, Doc]:
    docs: dict[str, Doc] = {}
    for d in domains:
        for f in sorted((root / "domains" / d.name / "kb").glob("*.md")):
            fm, body = marketplace.frontmatter(f.read_text())
            name = f"kb/{d.name}/{f.stem}"
            docs[name] = Doc(name, str(fm.get("description", f.stem)), body)
    return docs


def subagents(domains: list[Domain]) -> dict[str, dict[str, Any]]:
    return {sid: {**spec, "domain": d.name} for d in domains for sid, spec in d.subagents.items()}
