"""Response models for the API (ROADMAP-100 063): the OpenAPI schema says what each endpoint returns, so the
dashboard's types can be generated from it instead of written by hand."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class RunSummary(BaseModel):
    """One row of the run list (`data.summary`)."""

    run_id: str
    issue_ref: str | None = None
    issue_id: str | None = None
    source: str | None = None
    title: str | None = None
    app: str | None = None
    version: str | None = None
    status: str | None = None
    llm_mode: str | None = None
    started_at: str | None = None
    priority: str | None = None
    severity: str | None = None
    owner: str | None = None
    oncall: str | None = None
    customer_impacting: float | None = None
    worth_agent_run: float | None = None
    jira: str | None = None
    category: str | None = None
    location: str | None = None
    validated: bool = False
    tier: str | None = None
    outcome: str | None = None
    pr: str | None = None
    watch: str | None = None
    cost_usd: float = 0.0
    seconds: float = 0.0


class Health(BaseModel):
    status: str


class HealthDeps(BaseModel):
    status: str
    runs_dir: str
    app_queue: str
    ledger: str


class AppMetrics(BaseModel):
    """Running totals of the App's poll; keys appear as events happen (`app_cli.count`)."""

    model_config = ConfigDict(extra="allow")
    runs_started: int = 0
    runs_done: int = 0
    runs_failed: int = 0
    retries: int = 0
    runs_given_up: int = 0
    not_onboarded: int = 0
    rate_limited: int = 0
    errors: int = 0
    updated_at: float | None = None
