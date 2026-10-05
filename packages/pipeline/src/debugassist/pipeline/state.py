"""Run state carried through every node (nothing is forgotten between steps)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from debugassist.core.evidence import EvidenceItem

Category = Literal["own_code", "third_party_lib", "infra", "network", "flag_config", "device_os", "not_a_bug"]


class Issue(BaseModel):
    source: Literal["vitals", "bugdrop"]
    id: str
    url: str
    title: str
    kind: str
    app: str
    platform: str
    version: str
    first_version: str
    last_version: str
    fingerprint: str | None = None
    events: int = 0
    culprit: str | None = None
    repo: str  # target repository name
    gh_repo: str  # owner/name
    component: str  # component dir in the repo ("." for the client)
    language: str
    latest_event: dict[str, Any] = Field(default_factory=dict[str, Any])
    session_id: str | None = None
    report: dict[str, Any] = Field(default_factory=dict[str, Any])  # BugDrop: the report as filed


class Triage(BaseModel):
    priority: str
    severity: str
    owner_team: str
    oncall: str
    owner_source: str  # codeowners | clef
    customer_impacting: float
    worth_agent_run: float
    jira_key: str | None = None
    jira_url: str | None = None
    jira_mode: str | None = None
    duplicate_of: str | None = None  # D2: an open issue/report with the same root cause
    dedup: dict[str, Any] | None = None


class CodeLocation(BaseModel):
    repo: str
    file: str = Field(description="repo-relative path")
    function: str
    line: int | None = None


class Claim(BaseModel):
    text: str = Field(description="one factual statement")
    evidence_ids: list[str] = Field(description="evidence_id values (ev_…) that support the statement")


class TimelineEvent(BaseModel):
    when: str = Field(description="timestamp or relative time, e.g. 'release 1.6.1' or '0.2 s after launch'")
    event: str
    evidence_ids: list[str] = Field(default_factory=list[str])


class RCAOutput(BaseModel):
    summary: str = Field(description="2-3 sentences a busy engineer can act on")
    category: Category
    root_cause: str = Field(description="the defect and the mechanism that turns it into the symptom")
    location: CodeLocation
    suspect_commit: str | None = Field(
        default=None, description="sha of the commit that introduced the defect, if found"
    )
    implicated_flag: str | None = Field(
        default=None, description="feature flag gating the faulty path, if any"
    )
    claims: list[Claim] = Field(description="every factual claim with its evidence ids")
    timeline: list[TimelineEvent] = Field(description="what happened, in order, grounded in evidence")
    reproduction: str = Field(description="how to reproduce in a test")
    fix_direction: str = Field(description="what a correct fix should do (not code)")


class RCA(BaseModel):
    output: RCAOutput | None = None
    category_decision: dict[str, Any] = Field(default_factory=dict[str, Any])
    actionable: bool = True
    llm: dict[str, Any] = Field(default_factory=dict[str, Any])


class Mitigation(BaseModel):
    flag: str | None = None
    correlation: dict[str, Any] = Field(default_factory=dict[str, Any])
    decision: dict[str, Any] = Field(default_factory=dict[str, Any])
    action: Literal["none", "rolled_back", "dry_run", "awaiting_approval"] = "none"
    detail: str = ""


class ReproOutput(BaseModel):
    test_file: str = Field(description="repo-relative path of the reproduction test")
    asserts: str = Field(description="the correct behaviour the test asserts")
    failure: str = Field(
        description="the failure you observed on the current code (error message / assertion)"
    )


class FixOutput(BaseModel):
    commit_title: str = Field(
        description="conventional commit title, e.g. 'fix(notifications): wait for session restore in router v2'"
    )
    summary: str = Field(description="what changed, one paragraph")
    rationale: str = Field(description="why this fixes the root cause")
    strategy: str = Field(description="e.g. guard/null-safety, lifecycle, race/ordering, config change")
    risk: Literal["low", "medium", "high"]
    tests_added: list[str] = Field(description="repo-relative paths of new or changed test files")


class FixAttempt(BaseModel):
    n: int
    repro: ReproOutput | None = None
    repro_verified: bool = False
    repro_run: dict[str, Any] = Field(default_factory=dict[str, Any])
    output: FixOutput | None = None
    diff: str = ""
    files: list[str] = Field(default_factory=list[str])
    llm: dict[str, Any] = Field(default_factory=dict[str, Any])


class TestRun(BaseModel):
    label: str
    command: str
    exit_code: int
    output_tail: str


class Validation(BaseModel):
    attempts: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])
    passed: bool = False
    failing_before: TestRun | None = None
    passing_after: TestRun | None = None
    suite: TestRun | None = None
    static: TestRun | None = None  # the repo's CI lint/typecheck


ShipOutcome = Literal["open_pr", "draft_pr", "rca_only", "escalate"]


class Ship(BaseModel):
    outcome: ShipOutcome
    risk: float | None = None
    decision: dict[str, Any] = Field(default_factory=dict[str, Any])


class PRInfo(BaseModel):
    url: str
    number: int
    branch: str
    base: str
    draft: bool
    mode: str


class RunState(BaseModel):
    run_id: str
    issue_ref: str
    mode: Literal["autonomous", "supervised"] = "autonomous"
    llm_mode: Literal["live", "replay", "mock"] = "live"
    issue: Issue | None = None
    triage: Triage | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list[EvidenceItem])
    rca: RCA | None = None
    mitigation: Mitigation | None = None
    fix_attempts: list[FixAttempt] = Field(default_factory=list[FixAttempt])
    validation: Validation | None = None
    ship: Ship | None = None
    pr: PRInfo | None = None
    notifications: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])
    decisions: list[str] = Field(default_factory=list[str])  # ledger ids
    costs: dict[str, float] = Field(default_factory=dict[str, float])
    timings_ms: dict[str, int] = Field(default_factory=dict[str, int])
    errors: list[str] = Field(default_factory=list[str])
    status: Literal["running", "done", "failed", "stopped", "duplicate"] = "running"
    evidence_pruned: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])  # dropped by D3
    screenshots: dict[str, Any] | None = None  # D4 findings
