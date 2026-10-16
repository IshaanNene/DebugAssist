"""Everything a run needs from the outside world, built once per run (live or mock per integration)."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import yaml

from debugassist.core import ablation
from debugassist.core.policy import ROOT, PolicyGate
from debugassist.core.settings import Integration, Mode, Settings, get_settings
from debugassist.decisions.engine import DecisionEngine
from debugassist.decisions.factory import build_engine
from debugassist.harness import agent_types
from debugassist.integrations.chat import Chat, ChatMock, DiscordWebhook
from debugassist.integrations.github import GitHub, GitHubLive, GitHubMock, PullRequest
from debugassist.integrations.github_app import GitHubApp, GitHubAppLive, GitHubAppMock
from debugassist.integrations.jira import Jira, JiraCloud, JiraMock
from debugassist.llm.runner import CASSETTES, AgentRunner, CassetteRunner, LLMRunner, ScriptedRunner

SCRIPTED = ROOT / "packages" / "llm" / "scripted"

# Vitals app name → (target repo, GitHub repo, component dir, language)
APPS: dict[str, tuple[str, str, str, str]] = {
    "miniride-client": ("miniride-client", "IshaanNene/miniride-client", ".", "typescript"),
    "gateway": ("miniride-services", "IshaanNene/miniride-services", "gateway", "typescript"),
    "dispatch": ("miniride-services", "IshaanNene/miniride-services", "dispatch", "python"),
    "payments": ("miniride-services", "IshaanNene/miniride-services", "payments", "go"),
}


# Mock Clef answers are pseudo-random per state; pin the ones that would stop a keyless run before it
# writes a fix or opens a PR (e.g. a random non-code category, "needs a human" strategy or "cannot reproduce"
# tier). Labelled mock as always.
MOCK_DECISIONS: dict[str, Any] = {
    "category": "own_code",
    "rollback_flag": 0.93,
    "strategy": "race_ordering",
    "tier": "unit",
    "outcome": "open_pr",
}


@dataclass
class Deps:
    run_id: str
    settings: Settings
    engine: DecisionEngine
    gate: PolicyGate
    jira: Jira
    github: GitHub
    chat: Chat
    agent_type: dict[str, Any]
    catalog: dict[str, Any]
    llm_mode: str
    replay_from: str | None = None
    scripted_scenario: str = "push-crash"
    # API base URLs (service names inside a runtime container) and the UI URLs people click (localhost).
    vitals_url: str = field(default_factory=lambda: os.environ.get("VITALS_URL", "http://localhost:8100"))
    vitals_ui: str = field(default_factory=lambda: os.environ.get("VITALS_UI_URL", "http://localhost:8100"))
    bugdrop_url: str = field(default_factory=lambda: os.environ.get("BUGDROP_URL", "http://localhost:8200"))
    bugdrop_ui: str = field(default_factory=lambda: os.environ.get("BUGDROP_UI_URL", "http://localhost:8200"))
    extra: dict[str, Any] = field(default_factory=dict[str, Any])
    app: GitHubApp | None = None  # the GitHub App (GHA:… issues), live or mock; None when not configured

    @property
    def run_dir(self) -> Path:
        return ROOT / ".data" / "runs" / self.run_id

    def runner(self, apply_diff: Callable[[str], None] | None = None) -> LLMRunner:
        if self.llm_mode == "live":
            return AgentRunner(record_dir=CASSETTES / self.run_id, live_dir=self.run_dir / "agents")
        if self.llm_mode == "replay":
            assert self.replay_from, "replay mode needs --replay-from <run_id>"
            return CassetteRunner(CASSETTES / self.replay_from, apply_diff)
        return ScriptedRunner(SCRIPTED / self.scripted_scenario, apply_diff)


def new_run_id(issue_ref: str) -> str:
    return f"{datetime.now(UTC):%Y%m%d-%H%M%S}-{issue_ref.lower()}"


def build_app(s: Settings) -> GitHubApp | None:
    """The GitHub App when it is configured: live with its id and key, mock when DA_MODE_GITHUB_APP=mock."""
    if s.da_mode_github_app is Mode.MOCK:
        return GitHubAppMock()
    if s.mode(Integration.GITHUB_APP) is Mode.LIVE and s.github_app_id and s.github_app_private_key_path:
        return GitHubAppLive(s.github_app_id, Path(s.github_app_private_key_path).expanduser().read_text())
    return None


class GitHubRouter:
    """The pipeline's GitHub client: installed repositories go through the app (REST and pushes as the app);
    everything else through the token client or the mock, as before."""

    def __init__(self, default: GitHub, app: GitHubApp) -> None:
        self.default, self.app = default, app

    def _for(self, repo: str) -> GitHub:
        return self.app.client(repo) or self.default

    def _repo_of(self, worktree: Path) -> str:
        url = subprocess.run(
            ["git", "remote", "get-url", "origin"], cwd=worktree, capture_output=True, text=True
        ).stdout.strip()
        m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
        return m.group(1) if m else ""

    def remote_branch_exists(self, repo: str, branch: str) -> bool:
        return self._for(repo).remote_branch_exists(repo, branch)

    def push(self, worktree: Path, branch: str) -> None:
        self._for(self._repo_of(worktree)).push(worktree, branch)

    def open_pr(self, repo: str, head: str, base: str, title: str, body: str, draft: bool) -> PullRequest:
        return self._for(repo).open_pr(repo, head, base, title, body, draft)

    def comment(self, repo: str, number: int, body: str) -> None:
        self._for(repo).comment(repo, number, body)

    def merged(self, repo: str, number: int) -> bool | None:
        return self._for(repo).merged(repo, number)


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
    app = build_app(s)
    if app is not None:
        github = GitHubRouter(github, app)
    # DA_DECIDER (evaluations): routed = each template's own Clef model; clef / clef-flash = one model for
    # every decision; llm = no Clef (the LLM decides with self-reported confidence).
    which = ablation.decider()
    engine = await build_engine(
        s,
        "llm" if which == "llm" and s.mode(Integration.LLM) is Mode.LIVE else "auto",
        mock_overrides=MOCK_DECISIONS,
        model_override=cast(Any, which) if which in ("clef", "clef-flash") else None,
    )
    agent_type = agent_types.load(agent_types.DEFAULT).model_dump()  # re-resolved per issue at ingest
    catalog = yaml.safe_load((ROOT / "configs" / "catalog.yaml").read_text())
    os.environ["DEBUGASSIST_RUN_ID"] = run_id
    os.environ["DEBUGASSIST_MODE"] = mode
    return Deps(
        run_id=run_id,
        settings=s,
        engine=engine,
        gate=PolicyGate(mode=mode, installed=app.installed_repos if app else None),
        jira=jira,
        github=github,
        app=app,
        chat=(
            DiscordWebhook(s.discord_webhook_url.get_secret_value())
            if s.mode(Integration.CHAT) is Mode.LIVE and s.discord_webhook_url
            else ChatMock()
        ),
        agent_type=agent_type,
        catalog=catalog,
        llm_mode=llm_mode,
        replay_from=replay_from,
    )
