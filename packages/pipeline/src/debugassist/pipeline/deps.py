"""Everything a run needs from the outside world, built once per run (live or mock per integration)."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from debugassist.core.policy import ROOT, PolicyGate
from debugassist.core.settings import Integration, Mode, Settings, get_settings
from debugassist.decisions.engine import DecisionEngine
from debugassist.decisions.factory import build_engine
from debugassist.integrations.github import GitHub, GitHubLive, GitHubMock
from debugassist.integrations.jira import Jira, JiraCloud, JiraMock
from debugassist.integrations.slack import SlackMock
from debugassist.llm.runner import CASSETTES, AgentRunner, CassetteRunner, LLMRunner, ScriptedRunner

SCRIPTED = ROOT / "packages" / "llm" / "scripted"

# Vitals app name → (target repo, GitHub repo, component dir, language)
APPS: dict[str, tuple[str, str, str, str]] = {
    "miniride-client": ("miniride-client", "IshaanNene/miniride-client", ".", "typescript"),
    "gateway": ("miniride-services", "IshaanNene/miniride-services", "gateway", "typescript"),
    "dispatch": ("miniride-services", "IshaanNene/miniride-services", "dispatch", "python"),
    "payments": ("miniride-services", "IshaanNene/miniride-services", "payments", "go"),
}


@dataclass
class Deps:
    run_id: str
    settings: Settings
    engine: DecisionEngine
    gate: PolicyGate
    jira: Jira
    github: GitHub
    slack: SlackMock
    agent_type: dict[str, Any]
    catalog: dict[str, Any]
    llm_mode: str
    replay_from: str | None = None
    scripted_scenario: str = "push-crash"
    vitals_url: str = "http://localhost:8100"
    vitals_ui: str = "http://localhost:8100"
    extra: dict[str, Any] = field(default_factory=dict[str, Any])

    @property
    def run_dir(self) -> Path:
        return ROOT / ".data" / "runs" / self.run_id

    def runner(self, apply_diff: Callable[[str], None] | None = None) -> LLMRunner:
        if self.llm_mode == "live":
            return AgentRunner(record_dir=CASSETTES / self.run_id)
        if self.llm_mode == "replay":
            assert self.replay_from, "replay mode needs --replay-from <run_id>"
            return CassetteRunner(CASSETTES / self.replay_from, apply_diff)
        return ScriptedRunner(SCRIPTED / self.scripted_scenario, apply_diff)


def new_run_id(issue_ref: str) -> str:
    return f"{datetime.now(UTC):%Y%m%d-%H%M%S}-{issue_ref.lower()}"


async def build_deps(
    run_id: str, *, mode: str, llm_mode: str, replay_from: str | None = None, settings: Settings | None = None
) -> Deps:
    s = settings or get_settings()
    jira: Jira
    if s.mode(Integration.JIRA) is Mode.LIVE:
        assert s.jira_base_url and s.jira_email and s.jira_api_key
        jira = JiraCloud(
            s.jira_base_url,
            s.jira_email,
            s.jira_api_key.get_secret_value(),
            os.environ.get("JIRA_PROJECT_KEY", "SCRUM"),
        )
    else:
        jira = JiraMock()
    github: GitHub = (
        GitHubLive(s.github_token.get_secret_value())
        if s.mode(Integration.GITHUB) is Mode.LIVE and s.github_token
        else GitHubMock()
    )
    engine = await build_engine(s, "auto")
    agent_type = yaml.safe_load((ROOT / "configs" / "agent_types" / "web-crash.yaml").read_text())
    catalog = yaml.safe_load((ROOT / "configs" / "catalog.yaml").read_text())
    os.environ["DEBUGASSIST_RUN_ID"] = run_id
    os.environ["DEBUGASSIST_MODE"] = mode
    return Deps(
        run_id=run_id,
        settings=s,
        engine=engine,
        gate=PolicyGate(mode=mode),
        jira=jira,
        github=github,
        slack=SlackMock(),
        agent_type=agent_type,
        catalog=catalog,
        llm_mode=llm_mode,
        replay_from=replay_from,
    )
