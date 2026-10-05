"""The marketplace: plugins of markdown skills, fetched at a pinned git ref.

    marketplace/plugins/<plugin>/plugin.yaml          name, version, description, owners, skills
    marketplace/plugins/<plugin>/skills/<skill>/SKILL.md   frontmatter (name, description) + body
    marketplace/domains/<domain>/domain.yaml          see domains.py

`fetch(ref)` materialises the marketplace as of a git ref under .data/marketplace/<sha>/ (the working
checkout for ref "working"), so a run, a PEX or a runtime image uses exactly the skills it was built with.
Contributors add skills with no code and no redeploy: a PR to marketplace/, checked by `make lint-skills`.
"""

from __future__ import annotations

import io
import os
import re
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import BaseModel, ConfigDict

from debugassist.core.policy import ROOT

WORKING = ROOT / "marketplace"
CACHE = ROOT / ".data" / "marketplace"
EXPECTED_PLUGINS = 5
MAX_DESCRIPTION = 300
FORBIDDEN = re.compile(r"\bBUG-\d{3}\b|groundtruth|ground truth|hidden test|catalog id", re.I)


class Plugin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    version: str
    description: str
    owners: list[str]
    skills: list[str]


@dataclass(frozen=True)
class Skill:
    name: str
    plugin: str
    description: str
    body: str
    path: Path

    @property
    def tokens(self) -> int:
        return len(self.body) // 4


def ref_for(agent_ref: str) -> str:
    return os.environ.get("DA_MARKETPLACE_REF") or agent_ref


def fetch(ref: str = "working", repo: Path = ROOT) -> Path:
    """The marketplace directory as of `ref` (cached by commit sha)."""
    if ref == "working":
        return repo / "marketplace"
    sha = subprocess.run(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    out = CACHE / sha
    if (out / "marketplace").is_dir():
        return out / "marketplace"
    archive = subprocess.run(
        ["git", "archive", "--format=tar", sha, "marketplace"], cwd=repo, capture_output=True, check=True
    ).stdout
    out.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(out, filter="data")
    return out / "marketplace"


def frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    _, fm, body = text.split("---", 2)
    data = yaml.safe_load(fm)
    return (cast(dict[str, Any], data) if isinstance(data, dict) else {}), body.strip()


def plugins(root: Path = WORKING) -> dict[str, Plugin]:
    out: dict[str, Plugin] = {}
    for f in sorted(root.glob("plugins/*/plugin.yaml")):
        p = Plugin.model_validate(yaml.safe_load(f.read_text()))
        out[p.name] = p
    return out


def skills(root: Path = WORKING) -> dict[str, Skill]:
    out: dict[str, Skill] = {}
    for f in sorted(root.glob("plugins/*/skills/*/SKILL.md")):
        fm, body = frontmatter(f.read_text())
        name = str(fm.get("name", f.parent.name))
        out[name] = Skill(name, f.parts[-4], str(fm.get("description", "")), body, f)
    return out


def find(name: str, root: Path = WORKING) -> Path | None:
    s = skills(root).get(name)
    return s.path if s else None


def lint(root: Path = WORKING, agent_types: dict[str, Any] | None = None) -> list[str]:
    """Problems that block a marketplace change (empty = OK)."""
    problems: list[str] = []
    ps = plugins(root)
    if len(ps) != EXPECTED_PLUGINS:
        problems.append(f"expected exactly {EXPECTED_PLUGINS} plugins, found {len(ps)}: {sorted(ps)}")
    ss = skills(root)
    for p in ps.values():
        d = root / "plugins" / p.name
        if not (d / "plugin.yaml").is_file():
            problems.append(f"{p.name}: plugin directory name must equal its name")
        if not p.owners:
            problems.append(f"{p.name}: needs at least one owner")
        for s in p.skills:
            if s not in ss or ss[s].plugin != p.name:
                problems.append(f"{p.name}: lists skill {s!r} but has no skills/{s}/SKILL.md")
    for s in ss.values():
        if s.path.parent.name != s.name:
            problems.append(f"{s.path}: frontmatter name {s.name!r} must match its directory")
        if not s.description or len(s.description) > MAX_DESCRIPTION:
            problems.append(f"{s.name}: description is required and at most {MAX_DESCRIPTION} chars")
        if s.plugin not in ps or s.name not in ps[s.plugin].skills:
            problems.append(f"{s.name}: not listed in its plugin.yaml")
        if m := FORBIDDEN.search(s.body + s.description):
            problems.append(f"{s.name}: mentions {m.group(0)!r}; skills must not carry evaluation answers")
    for name, t in (agent_types or {}).items():
        budget = int(getattr(t, "skill_token_budget", 0) or 0)
        for node, names in dict(getattr(t, "skills", {}) or {}).items():
            missing = [n for n in names if n not in ss]
            if missing:
                problems.append(f"agent type {name}: node {node} loads unknown skills {missing}")
            total = sum(ss[n].tokens for n in names if n in ss)
            if budget and total > budget:
                problems.append(f"agent type {name}: node {node} skills are {total} tokens > budget {budget}")
    return problems
