"""Vitals HTTP API (ingest + REST) and a small server-rendered UI."""

from __future__ import annotations

import logging
import os
import re
from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from vitals_service import ingest, queries
from vitals_service.db import (
    AppSession,
    Base,
    Event,
    Group,
    Issue,
    IssueLink,
    make_engine,
    make_sessionmaker,
)
from vitals_service.models import EventBatch, LinkIn, SessionIn

log = logging.getLogger("vitals")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

engine = make_engine()
SessionLocal = make_sessionmaker(engine)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
SOURCEMAP_ORIGIN = os.environ.get("VITALS_SOURCEMAP_ORIGIN")  # e.g. http://client:8080 inside compose
WEBHOOK_URL = os.environ.get("VITALS_WEBHOOK_URL")
ORIGIN = re.compile(r"^\w+://[^/]+")


def fetch_map(url: str) -> str | None:
    if SOURCEMAP_ORIGIN:
        url = ORIGIN.sub(SOURCEMAP_ORIGIN, url)
    try:
        r = httpx.get(url, timeout=5)
        return r.text if r.status_code == 200 else None
    except httpx.HTTPError:
        return None


def notify(event_type: str, issue: Issue, group: Group) -> None:
    log.info("%s %s %s", event_type, issue.id, issue.title)
    if not WEBHOOK_URL:
        return
    try:
        httpx.post(
            WEBHOOK_URL,
            json={"type": event_type, "source": "vitals", "issue": issue_out(issue, group)},
            timeout=3,
        )
    except httpx.HTTPError:
        log.warning("webhook delivery failed")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Vitals", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("VITALS_CORS_ORIGINS", "http://localhost:8080,http://localhost:5173").split(
        ","
    ),
    allow_methods=["POST", "GET"],
    allow_headers=["content-type"],
)


def db() -> Iterator[DbSession]:
    with SessionLocal() as s:
        yield s


DB = Annotated[DbSession, Depends(db)]


def group_out(g: Group) -> dict[str, Any]:
    return {
        "fingerprint": g.fingerprint,
        "app": g.app,
        "platform": g.platform,
        "kind": g.kind,
        "title": g.title,
        "culprit": g.culprit,
        "first_seen": g.first_seen.isoformat(),
        "last_seen": g.last_seen.isoformat(),
        "first_version": g.first_version,
        "last_version": g.last_version,
        "count": g.count,
        "status": g.status,
        "issue_id": g.issue_id,
    }


def issue_out(i: Issue, g: Group | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": i.id,
        "title": i.title,
        "kind": i.kind,
        "app": i.app,
        "status": i.status,
        "reason": i.reason,
        "version": i.version,
        "opened_at": i.opened_at.isoformat(),
        "fingerprint": i.fingerprint,
        "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
    }
    if g is not None:
        out["group"] = group_out(g)
    return out


def event_out(e: Event, full: bool = False) -> dict[str, Any]:
    p = e.payload
    out: dict[str, Any] = {
        "id": e.id,
        "kind": e.kind,
        "app": e.app,
        "platform": e.platform,
        "version": e.version,
        "session_id": e.session_id,
        "ts": e.ts.isoformat(),
        "title": e.title,
        "culprit": e.culprit,
        "flags": p.get("flags", {}),
        "device": p.get("device", {}),
        "trace_id": p.get("trace_id"),
    }
    if full:
        out |= {
            "error": p.get("error"),
            "perf": p.get("perf"),
            "frames": p.get("frames", []),
            "raw_frames": p.get("raw_frames"),
            "symbolicated": p.get("symbolicated", False),
            "breadcrumbs": p.get("breadcrumbs", []),
            "logs": p.get("logs", []),
            "tags": p.get("tags", {}),
        }
    return out


# ---- ingest ---------------------------------------------------------------------------------


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/sessions", status_code=202)
def post_session(body: SessionIn, s: DB) -> dict[str, str]:
    ingest.upsert_session(s, body)
    s.commit()
    return {"status": "accepted"}


@app.post("/v1/events", status_code=202)
def post_events(body: EventBatch, s: DB) -> dict[str, Any]:
    ids: list[str] = []
    for e in body.events:
        ids.append(ingest.process_event(s, e, fetch_map, notify).fingerprint)
        s.commit()
    return {"accepted": len(ids), "fingerprints": ids}


# ---- REST -----------------------------------------------------------------------------------


@app.get("/api/issues")
def list_issues(
    s: DB,
    status: str | None = None,
    app_name: Annotated[str | None, Query(alias="app")] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    stmt = select(Issue).order_by(Issue.opened_at.desc()).limit(min(limit, 200))
    if status:
        stmt = stmt.where(Issue.status == status)
    if app_name:
        stmt = stmt.where(Issue.app == app_name)
    return [issue_out(i, s.get(Group, i.fingerprint)) for i in s.scalars(stmt)]


def _issue(s: DbSession, issue_id: str) -> Issue:
    i = s.get(Issue, issue_id)
    if i is None:
        raise HTTPException(404, "issue not found")
    return i


@app.get("/api/issues/{issue_id}")
def get_issue(issue_id: str, s: DB) -> dict[str, Any]:
    i = _issue(s, issue_id)
    g = s.get(Group, i.fingerprint)
    latest = s.scalars(
        select(Event).where(Event.fingerprint == i.fingerprint).order_by(Event.ts.desc()).limit(1)
    ).first()
    out = issue_out(i, g)
    out["latest_event"] = event_out(latest, full=True) if latest else None
    out["links"] = _links(s, issue_id)
    return out


def _links(s: DbSession, issue_id: str) -> list[dict[str, Any]]:
    rows = s.scalars(select(IssueLink).where(IssueLink.issue_id == issue_id).order_by(IssueLink.id))
    return [
        {"kind": r.kind, "url": r.url, "title": r.title, "created_at": r.created_at.isoformat()} for r in rows
    ]


@app.post("/api/issues/{issue_id}/links", status_code=201)
def add_link(issue_id: str, link: LinkIn, s: DB) -> list[dict[str, Any]]:
    """Attach a Jira ticket / PR / RCA to the issue; the same URL is only stored once."""
    _issue(s, issue_id)
    exists = s.scalars(
        select(IssueLink).where(IssueLink.issue_id == issue_id, IssueLink.url == link.url)
    ).first()
    if exists is None:
        s.add(IssueLink(issue_id=issue_id, kind=link.kind, url=link.url, title=link.title))
        s.commit()
    return _links(s, issue_id)


@app.post("/api/issues/{issue_id}/resolve")
def resolve_issue(issue_id: str, s: DB, version: str | None = None) -> dict[str, Any]:
    i = _issue(s, issue_id)
    ingest.resolve(s, i, version)
    s.commit()
    return issue_out(i, s.get(Group, i.fingerprint))


def _group(s: DbSession, fp: str) -> Group:
    g = s.get(Group, fp)
    if g is None:
        raise HTTPException(404, "group not found")
    return g


@app.get("/api/groups/{fp}")
def get_group(fp: str, s: DB) -> dict[str, Any]:
    return group_out(_group(s, fp))


@app.get("/api/groups/{fp}/events")
def group_events(fp: str, s: DB, limit: int = 20, full: bool = False) -> list[dict[str, Any]]:
    _group(s, fp)
    rows = s.scalars(
        select(Event).where(Event.fingerprint == fp).order_by(Event.ts.desc()).limit(min(limit, 100))
    )
    return [event_out(e, full) for e in rows]


@app.get("/api/groups/{fp}/distribution")
def group_distribution(fp: str, s: DB, by: str = "version") -> dict[str, Any]:
    if by not in queries.DIMENSIONS and not by.startswith("flag:"):
        raise HTTPException(400, f"by must be one of {queries.DIMENSIONS} or flag:<name>")
    return queries.distribution(s, _group(s, fp), by)


@app.get("/api/groups/{fp}/flags")
def group_flags(fp: str, s: DB) -> list[dict[str, Any]]:
    return queries.flag_exposure(s, _group(s, fp))


@app.get("/api/groups/{fp}/timeseries")
def group_timeseries(fp: str, s: DB, bucket_s: int = 300) -> list[dict[str, Any]]:
    _group(s, fp)
    return queries.timeseries(s, fp, bucket_s)


@app.get("/api/events/{event_id}")
def get_event(event_id: str, s: DB) -> dict[str, Any]:
    e = s.get(Event, event_id)
    if e is None:
        raise HTTPException(404, "event not found")
    return event_out(e, full=True)


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str, s: DB) -> dict[str, Any]:
    row = s.get(AppSession, session_id)
    if row is None:
        raise HTTPException(404, "session not found")
    events = s.scalars(select(Event).where(Event.session_id == session_id).order_by(Event.ts)).all()
    return {
        "id": row.id,
        "analytics_id": row.analytics_id,
        "app": row.app,
        "version": row.version,
        "os": row.os,
        "browser": row.browser,
        "device": row.device,
        "city": row.city,
        "locale": row.locale,
        "flags": row.flags,
        "started_at": row.started_at.isoformat(),
        "events": [event_out(e) for e in events],
    }


@app.get("/api/stats")
def get_stats(
    s: DB,
    since: datetime,
    until: datetime | None = None,
    fingerprint: str | None = None,
    app_name: Annotated[str, Query(alias="app")] = "miniride-client",
) -> dict[str, Any]:
    """Sessions (and one issue's affected sessions) in a time window."""
    return queries.window_stats(s, app_name, since, until or datetime.now(UTC), fingerprint)


@app.get("/api/releases")
def get_releases(
    s: DB, app_name: Annotated[str, Query(alias="app")] = "miniride-client"
) -> list[dict[str, Any]]:
    return queries.releases(s, app_name)


# ---- UI -------------------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def ui_issues(request: Request, s: DB) -> HTMLResponse:
    issues = list_issues(s, limit=100)
    return templates.TemplateResponse(request, "issues.html", {"issues": issues})


@app.get("/issues/{issue_id}", response_class=HTMLResponse)
def ui_issue(issue_id: str, request: Request, s: DB) -> HTMLResponse:
    detail = get_issue(issue_id, s)
    g = _group(s, detail["fingerprint"])
    ctx = {
        "issue": detail,
        "versions": queries.distribution(s, g, "version"),
        "flags": queries.flag_exposure(s, g),
        "cities": queries.distribution(s, g, "city"),
        "events": group_events(g.fingerprint, s, limit=10),
    }
    return templates.TemplateResponse(request, "issue.html", ctx)
