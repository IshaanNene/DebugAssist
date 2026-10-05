from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from debugassist.harness import agent_types, domains, launcher, marketplace, skills
from debugassist.harness.agent_types import AgentType


def skill(root: Path, plugin: str, name: str, body: str = "Be careful.", description: str = "d") -> None:
    d = root / "plugins" / plugin / "skills" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n")


def plugin(root: Path, name: str, skills_: list[str], owners: list[str] | None = None) -> None:
    (root / "plugins" / name).mkdir(parents=True, exist_ok=True)
    (root / "plugins" / name / "plugin.yaml").write_text(
        yaml.safe_dump(
            {
                "name": name,
                "version": "1.0.0",
                "description": "x",
                "owners": owners or ["team"],
                "skills": skills_,
            }
        )
    )


def market(root: Path, n: int = 5) -> Path:
    for i in range(n):
        plugin(root, f"p{i}", [f"s{i}"])
        skill(root, f"p{i}", f"s{i}", body="x" * 400)
    return root


def test_the_real_marketplace_passes_lint() -> None:
    assert marketplace.lint(marketplace.WORKING, agent_types.all_types()) == []
    assert len(marketplace.plugins()) == 5


def test_lint_catches_count_listing_answers_and_budget(tmp_path: Path) -> None:
    root = market(tmp_path, 4)
    skill(root, "p0", "leaky", body="The fix for BUG-003 is in rides.ts")
    t = AgentType(
        name="t",
        description="d",
        nodes={},
        skills={"fix": ["s0", "s1", "nope"]},
        skill_token_budget=150,
        runtime_image="i",
    )
    problems = marketplace.lint(root, {"t": t})
    assert any("exactly 5 plugins" in p for p in problems)
    assert any("leaky" in p and "BUG-003" in p for p in problems)
    assert any("not listed in its plugin.yaml" in p for p in problems)
    assert any("unknown skills ['nope']" in p for p in problems)
    assert any("200 tokens > budget 150" in p for p in problems)


def test_fetch_materialises_the_marketplace_at_a_git_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    market(repo / "marketplace")
    for args in (
        ["init", "-q"],
        ["add", "."],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "v1"],
    ):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    (repo / "marketplace" / "plugins" / "p0" / "skills" / "s0" / "SKILL.md").write_text(
        "---\nname: s0\ndescription: changed\n---\nnew"
    )
    monkeypatch.setattr(marketplace, "CACHE", tmp_path / "cache")
    pinned = marketplace.fetch("HEAD", repo)
    assert marketplace.skills(pinned)["s0"].description == "d"  # the committed version, not the edit
    assert marketplace.skills(marketplace.fetch("working", repo))["s0"].description == "changed"
    monkeypatch.setenv("DA_MARKETPLACE_REF", "v9")
    assert marketplace.ref_for("working") == "v9"


def test_progressive_disclosure_lists_then_loads_within_budget(tmp_path: Path) -> None:
    root = market(tmp_path)
    text = skills.catalog(["s0", "s1"], root)
    assert "- s0: d" in text and "x" * 50 not in text  # names and descriptions only
    load = skills.load_skill_tool(["s0", "s1"], root, budget_tokens=150)
    assert load.invoke({"name": "s0"}).startswith("# Skill: s0")
    assert "already loaded" in load.invoke({"name": "s0"})
    assert "budget" in load.invoke({"name": "s1"})  # 100 + 100 > 150
    assert "unknown skill" in load.invoke({"name": "s3"})  # exists, but not offered to this node


def test_agent_types_resolve_by_specificity_then_repo_default(tmp_path: Path) -> None:
    def write(name: str, priority: int, match: dict[str, list[str]]) -> None:
        (tmp_path / f"{name}.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": name,
                    "description": "d",
                    "priority": priority,
                    "match": match,
                    "nodes": {},
                    "runtime_image": f"img/{name}",
                }
            )
        )

    write("web-crash", 10, {"sources": ["vitals"], "kinds": ["crash"], "repos": ["miniride-client"]})
    write("perf-regression", 20, {"kinds": ["perf"]})
    write("backend-error", 10, {"repos": ["miniride-services"]})
    write("user-bug-report", 15, {"sources": ["bugdrop"]})

    def r(source: str, kind: str, repo: str, repo_default: str | None = None) -> str:
        return agent_types.resolve(
            source=source, kind=kind, repo=repo, language=None, repo_default=repo_default, directory=tmp_path
        )[0].name

    assert r(source="vitals", kind="perf", repo="miniride-client") == "perf-regression"
    assert r(source="bugdrop", kind="bug_report", repo="miniride-client") == "user-bug-report"
    assert (
        r(source="vitals", kind="crash", repo="miniride-services") == "backend-error"
    )  # tie → first max? no: equal priority
    assert r(source="other", kind="x", repo="elsewhere", repo_default="backend-error") == "backend-error"
    assert r(source="other", kind="x", repo="elsewhere") == "web-crash"
    t, why = agent_types.resolve(
        source="vitals", kind="crash", repo="x", language=None, override="perf-regression", directory=tmp_path
    )
    assert t.name == "perf-regression" and "requested" in why
    with pytest.raises(ValueError, match="unknown agent type"):
        agent_types.load("nope", tmp_path)


def test_domains_apply_by_component_and_bring_subagents_and_knowledge(tmp_path: Path) -> None:
    d = tmp_path / "domains" / "dispatch"
    (d / "kb").mkdir(parents=True)
    (d / "domain.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "dispatch",
                "description": "d",
                "owners": ["dispatch"],
                "components": [{"repo": "miniride-services", "path": "dispatch"}],
                "subagents": {
                    "matcher": {
                        "description": "m",
                        "inputs": ["logs"],
                        "mcp_servers": ["logging"],
                        "focus": "f",
                    }
                },
            }
        )
    )
    (d / "kb" / "service.md").write_text("---\ndescription: layout\n---\nThe app lives in src/.")
    hit = domains.for_issue(tmp_path, "miniride-services", "dispatch")
    assert [x.name for x in hit] == ["dispatch"] and domains.for_issue(
        tmp_path, "miniride-services", "payments"
    ) == []
    assert domains.subagents(hit)["matcher"]["domain"] == "dispatch"
    docs = domains.knowledge(tmp_path, hit)
    assert list(docs) == ["kb/dispatch/service"] and docs["kb/dispatch/service"].description == "layout"
    market(tmp_path)
    load = skills.load_skill_tool([], tmp_path, 1000, docs)
    assert "src/." in load.invoke({"name": "kb/dispatch/service"})


def test_the_real_domains_match_the_target_components() -> None:
    root = marketplace.WORKING
    assert [d.name for d in domains.for_issue(root, "miniride-client", ".")] == ["rider"]
    assert [d.name for d in domains.for_issue(root, "miniride-services", "payments")] == ["payments"]


def test_container_command_mounts_the_checkout_and_uses_service_names() -> None:
    cmd = launcher.container_command("perf-regression", "BD-1002", ["--llm", "mock"])
    root = str(launcher.ROOT)
    assert ["-v", f"{root}:{root}"] == cmd[cmd.index(f"{root}:{root}") - 1 : cmd.index(f"{root}:{root}") + 1]
    assert "/var/run/docker.sock:/var/run/docker.sock" in cmd and "VITALS_URL=http://vitals:8100" in cmd
    assert cmd[-6:] == ["--agent-type", "perf-regression", "--issue", "BD-1002", "--llm", "mock"]
    assert "debugassist/runtime-perf-regression" in cmd
    assert launcher.peek("BD-7")["source"] == "bugdrop"


def test_host_da_settings_reach_the_container(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DA_MODE_GITHUB", "mock")
    cmd = launcher.container_command("web-crash", "VIT-1", [])
    assert "DA_MODE_GITHUB=mock" in cmd and f"DEBUGASSIST_ROOT={launcher.ROOT}" in cmd
