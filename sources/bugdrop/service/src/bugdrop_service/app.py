"""BugDrop HTTP API: report intake (multipart), REST for logs/screenshots/timeline, and a small UI."""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bugdrop_service.blobs import BlobStore, from_env
from bugdrop_service.db import Base, Report, ReportLink, make_engine, make_sessionmaker
from bugdrop_service.timeline import ui_state_timeline
from debugassist.core.redaction import redact, redact_text

log = logging.getLogger("bugdrop")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

LOG_KINDS = ("network", "analytics", "console", "graphql", "ui_state", "perf")
IMAGE_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_ATTACHMENTS = 4

engine = make_engine()
SessionLocal = make_sessionmaker(engine)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
_store: BlobStore | None = None
WEBHOOK_URL = os.environ.get("BUGDROP_WEBHOOK_URL")


def store() -> BlobStore:
    global _store
    if _store is None:
        _store = from_env()
    return _store


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="BugDrop", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("BUGDROP_CORS_ORIGINS", "http://localhost:8080,http://localhost:5173").split(
        ","
    ),
    allow_methods=["POST", "GET"],
    allow_headers=["content-type"],
)


def db() -> Iterator[Session]:
    with SessionLocal() as s:
        yield s


DB = Annotated[Session, Depends(db)]


class DeviceIn(BaseModel):
    os: str | None = None
    browser: str | None = None
    device: str | None = None
    locale: str | None = None


class ReportIn(BaseModel):
    description: str = Field(min_length=1, max_length=4000)
    app: str
    version: str
    session_id: str | None = None
    analytics_id: str | None = None
    device: DeviceIn = Field(default_factory=DeviceIn)
    city: str | None = None
    route: str | None = None
    flags: dict[str, bool | str] = Field(default_factory=dict[str, bool | str])
    network: dict[str, Any] = Field(default_factory=dict[str, Any])  # effectiveType, rtt, downlink, saveData
    logs: dict[str, list[dict[str, Any]]] = Field(default_factory=dict[str, list[dict[str, Any]]])
    created_at: float | None = None


def report_out(r: Report) -> dict[str, Any]:
    return {
        "id": r.id,
        "created_at": r.created_at.isoformat(),
        "description": r.description,
        "app": r.app,
        "version": r.version,
        "session_id": r.session_id,
        "analytics_id": r.analytics_id,
        "device": {"os": r.os, "browser": r.browser, "device": r.device, "locale": r.locale},
        "city": r.city,
        "route": r.route,
        "flags": r.flags,
        "network": r.network,
        "log_counts": r.log_counts,
        "files": [
            {k: v for k, v in f.items() if k != "key"} | {"url": f"/api/reports/{r.id}/files/{f['name']}"}
            for f in r.files
        ],
        "status": r.status,
    }


def _image_type(upload: UploadFile, data: bytes) -> str:
    sniff = {b"\x89PNG": "image/png", b"\xff\xd8\xff": "image/jpeg", b"RIFF": "image/webp"}
    for magic, ctype in sniff.items():
        if data.startswith(magic):
            return ctype
    raise HTTPException(415, f"{upload.filename}: only PNG, JPEG or WebP images are accepted")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/reports", status_code=201)
async def create_report(
    s: DB,
    report: Annotated[str, Form()],
    screenshot: Annotated[UploadFile | None, File()] = None,
    attachments: Annotated[list[UploadFile] | None, File()] = None,
) -> dict[str, Any]:
    body = ReportIn.model_validate_json(report)
    if attachments and len(attachments) > MAX_ATTACHMENTS:
        raise HTTPException(413, f"at most {MAX_ATTACHMENTS} attachments")
    seq = (s.scalar(select(func.max(Report.seq))) or 1000) + 1
    rid = f"BD-{seq}"
    logs = {k: redact(body.logs.get(k, [])) for k in LOG_KINDS}  # server-side redaction (SDK also redacts)
    files: list[dict[str, Any]] = []
    uploads: list[tuple[str, UploadFile]] = []
    if screenshot is not None:
        uploads.append(("app_screenshot", screenshot))
    uploads += [("user_attachment", a) for a in attachments or []]
    for i, (kind, up) in enumerate(uploads):
        data = await up.read()
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(413, f"{up.filename}: image larger than {MAX_IMAGE_BYTES} bytes")
        ctype = _image_type(up, data)
        name = "screenshot.png" if kind == "app_screenshot" else f"attachment-{i}.{IMAGE_TYPES[ctype]}"
        key = f"reports/{rid}/{name}"
        store().put(key, data, ctype)
        files.append(
            {
                "name": name,
                "kind": kind,
                "content_type": ctype,
                "bytes": len(data),
                "key": key,
                "original_name": re.sub(r"[^\w.\- ]", "", up.filename or "")[:80],
            }
        )
    created = datetime.fromtimestamp(body.created_at, UTC) if body.created_at else datetime.now(UTC)
    bundle = {"report_ts": created.timestamp(), "logs": logs}
    store().put(f"reports/{rid}/logs.json", json.dumps(bundle).encode(), "application/json")
    row = Report(
        id=rid,
        seq=seq,
        created_at=created,
        description=redact_text(body.description),
        app=body.app,
        version=body.version,
        session_id=body.session_id,
        analytics_id=body.analytics_id,
        os=body.device.os,
        browser=body.device.browser,
        device=body.device.device,
        locale=body.device.locale,
        city=body.city,
        route=body.route,
        flags=body.flags,
        network=body.network,
        log_counts={k: len(v) for k, v in logs.items()},
        files=files,
    )
    s.add(row)
    s.commit()
    log.info("report %s from %s %s: %s", rid, body.app, body.version, row.description[:80])
    out = report_out(row)
    if WEBHOOK_URL:
        try:
            async with httpx.AsyncClient(timeout=3) as http:
                await http.post(
                    WEBHOOK_URL, json={"type": "report.created", "source": "bugdrop", "report": out}
                )
        except httpx.HTTPError:
            log.warning("webhook delivery failed")
    return out


def _report(s: Session, rid: str) -> Report:
    r = s.get(Report, rid)
    if r is None:
        raise HTTPException(404, "report not found")
    return r


def _bundle(r: Report) -> dict[str, Any]:
    raw = store().get(f"reports/{r.id}/logs.json")
    return json.loads(raw) if raw else {"report_ts": r.created_at.timestamp(), "logs": {}}


@app.get("/api/reports")
def list_reports(
    s: DB, app_name: str | None = None, since: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    stmt = select(Report).order_by(Report.created_at.desc()).limit(min(limit, 200))
    if app_name:
        stmt = stmt.where(Report.app == app_name)
    if since:
        stmt = stmt.where(Report.created_at >= datetime.fromisoformat(since))
    return [report_out(r) for r in s.scalars(stmt)]


@app.get("/api/reports/{rid}")
def get_report(rid: str, s: DB) -> dict[str, Any]:
    return {**report_out(_report(s, rid)), "links": _links(s, rid)}


class LinkIn(BaseModel):
    kind: Literal["jira", "pr", "rca", "other"] = "other"
    url: str = Field(min_length=1, max_length=2000)
    title: str = Field(default="", max_length=300)


class StatusIn(BaseModel):
    status: Literal["new", "triaged", "in_progress", "resolved", "duplicate"]


def _links(s: Session, rid: str) -> list[dict[str, Any]]:
    rows = s.scalars(select(ReportLink).where(ReportLink.report_id == rid).order_by(ReportLink.id))
    return [
        {"kind": r.kind, "url": r.url, "title": r.title, "created_at": r.created_at.isoformat()} for r in rows
    ]


@app.post("/api/reports/{rid}/links", status_code=201)
def add_link(rid: str, link: LinkIn, s: DB) -> list[dict[str, Any]]:
    """Attach a Jira ticket / PR / RCA to the report; the same URL is only stored once."""
    _report(s, rid)
    if (
        s.scalars(select(ReportLink).where(ReportLink.report_id == rid, ReportLink.url == link.url)).first()
        is None
    ):
        s.add(ReportLink(report_id=rid, kind=link.kind, url=link.url, title=link.title))
        s.commit()
    return _links(s, rid)


@app.post("/api/reports/{rid}/status")
def set_status(rid: str, body: StatusIn, s: DB) -> dict[str, Any]:
    r = _report(s, rid)
    r.status = body.status
    s.commit()
    return get_report(rid, s)


@app.get("/api/reports/{rid}/logs")
def get_logs(
    rid: str,
    s: DB,
    kind: str,
    q: str | None = None,
    since: float | None = None,
    until: float | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    if kind not in LOG_KINDS:
        raise HTTPException(400, f"kind must be one of {LOG_KINDS}")
    entries = _bundle(_report(s, rid))["logs"].get(kind, [])
    if since is not None:
        entries = [e for e in entries if float(e.get("ts", 0)) >= since]
    if until is not None:
        entries = [e for e in entries if float(e.get("ts", 0)) <= until]
    if q:
        needle = q.lower()
        entries = [e for e in entries if needle in json.dumps(e).lower()]
    limit = min(max(limit, 1), 1000)
    return {
        "kind": kind,
        "total": len(entries),
        "offset": offset,
        "entries": entries[offset : offset + limit],
    }


@app.get("/api/reports/{rid}/screenshots")
def get_screenshots(rid: str, s: DB) -> list[dict[str, Any]]:
    return report_out(_report(s, rid))["files"]


@app.get("/api/reports/{rid}/files/{name}")
def get_file(rid: str, name: str, s: DB) -> Response:
    r = _report(s, rid)
    f = next((f for f in r.files if f["name"] == name), None)
    data = store().get(f["key"]) if f else None
    if f is None or data is None:
        raise HTTPException(404, "file not found")
    return Response(data, media_type=f["content_type"])


@app.get("/api/reports/{rid}/ui-state-timeline")
def get_timeline(rid: str, s: DB) -> dict[str, Any]:
    b = _bundle(_report(s, rid))
    return ui_state_timeline(b["logs"].get("ui_state", []), float(b["report_ts"]))


@app.get("/", response_class=HTMLResponse)
def ui_list(request: Request, s: DB) -> HTMLResponse:
    return templates.TemplateResponse(request, "reports.html", {"reports": list_reports(s, limit=100)})


@app.get("/reports/{rid}", response_class=HTMLResponse)
def ui_report(rid: str, request: Request, s: DB, kind: str = "network") -> HTMLResponse:
    report = get_report(rid, s)
    logs = get_logs(rid, s, kind=kind if kind in LOG_KINDS else "network", limit=300)
    timeline = get_timeline(rid, s)
    ctx = {"r": report, "logs": logs, "kind": kind, "kinds": LOG_KINDS, "timeline": timeline}
    return templates.TemplateResponse(request, "report.html", ctx)
