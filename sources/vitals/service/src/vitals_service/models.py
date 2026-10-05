"""Wire models for SDK ingestion."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

EventKind = Literal["crash", "exception", "hang", "jank", "perf"]
Platform = Literal["web", "python", "go", "node"]


class Frame(BaseModel):
    function: str = "?"
    file: str = "?"
    line: int | None = None
    col: int | None = None
    in_app: bool = True


class ErrorInfo(BaseModel):
    type: str
    message: str = ""
    stack: str | None = None  # raw text (JS/Node); parsed server-side
    frames: list[Frame] | None = None  # structured (Python/Go SDKs), innermost last


class Breadcrumb(BaseModel):
    ts: float
    category: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict[str, Any])


class LogLine(BaseModel):
    ts: float
    level: str = "info"
    message: str


class Device(BaseModel):
    os: str | None = None
    browser: str | None = None
    device: str | None = None
    city: str | None = None
    locale: str | None = None


class PerfInfo(BaseModel):
    metric: str  # cpu_busy_hidden | memory_growth | slow_request | long_tasks | main_thread_blocked
    value: float
    unit: str = ""
    window_s: float | None = None
    details: dict[str, Any] = Field(default_factory=dict[str, Any])


class EventIn(BaseModel):
    event_id: str
    kind: EventKind
    app: str
    platform: Platform
    version: str
    ts: float  # epoch seconds
    session_id: str | None = None
    analytics_id: str | None = None
    error: ErrorInfo | None = None
    perf: PerfInfo | None = None
    culprit: str | None = None  # route / endpoint / screen
    breadcrumbs: list[Breadcrumb] = Field(default_factory=list[Breadcrumb], max_length=100)
    logs: list[LogLine] = Field(default_factory=list[LogLine], max_length=200)
    flags: dict[str, bool | str] = Field(default_factory=dict[str, bool | str])
    device: Device = Field(default_factory=Device)
    tags: dict[str, str] = Field(default_factory=dict[str, str])
    trace_id: str | None = None


class EventBatch(BaseModel):
    events: list[EventIn] = Field(max_length=100)


class SessionIn(BaseModel):
    session_id: str
    analytics_id: str | None = None
    app: str
    platform: Platform = "web"
    version: str
    started_at: datetime | None = None
    flags: dict[str, bool | str] = Field(default_factory=dict[str, bool | str])
    device: Device = Field(default_factory=Device)


class LinkIn(BaseModel):
    kind: Literal["jira", "pr", "rca", "other"] = "other"
    url: str = Field(min_length=1, max_length=2000)
    title: str = Field(default="", max_length=300)
