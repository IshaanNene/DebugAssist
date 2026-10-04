"""Event processing: symbolicate → fingerprint → group → issue (new / regression) → webhook."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from vitals_service.db import AppSession, Event, Group, Issue
from vitals_service.models import EventIn, Frame, SessionIn
from vitals_service.stacks import MapFetcher, fingerprint, parse_stack, symbolicate

log = logging.getLogger("vitals.ingest")

# Non-crash kinds need repeated evidence before they become issues.
ISSUE_THRESHOLD = {"crash": 1, "exception": 1, "hang": 1, "perf": 1, "jank": 3}

Notify = Callable[[str, Issue, Group], None]


def version_key(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


def upsert_session(db: DbSession, s: SessionIn) -> None:
    row = db.get(AppSession, s.session_id)
    if row is None:
        row = AppSession(id=s.session_id, started_at=s.started_at or datetime.now(UTC))
        db.add(row)
    row.analytics_id = s.analytics_id
    row.app, row.platform, row.version = s.app, s.platform, s.version
    row.os, row.browser, row.device = s.device.os, s.device.browser, s.device.device
    row.city, row.locale = s.device.city, s.device.locale
    row.flags = {**(row.flags or {}), **s.flags}


def _title(e: EventIn) -> str:
    if e.error:
        msg = e.error.message.splitlines()[0] if e.error.message else ""
        return f"{e.error.type}: {msg}"[:300]
    if e.perf:
        return f"{e.perf.metric} {e.perf.value:g}{e.perf.unit}"[:300]
    return e.kind


def _culprit(e: EventIn, frames: list[Frame]) -> str | None:
    if e.culprit:
        return e.culprit
    in_app = [f for f in frames if f.in_app]
    if in_app:
        f = in_app[-1]
        return f"{f.function} ({f.file}:{f.line})"
    return None


def process_event(db: DbSession, e: EventIn, fetch_map: MapFetcher, notify: Notify | None = None) -> Event:
    frames: list[Frame] = []
    raw_frames: list[Frame] = []
    symbolicated = False
    if e.error:
        raw_frames = e.error.frames or (parse_stack(e.error.stack) if e.error.stack else [])
        frames, symbolicated = (
            symbolicate(raw_frames, fetch_map) if e.platform == "web" else (raw_frames, False)
        )
    fp = fingerprint(
        e.kind, e.app, e.error.type if e.error else None, frames, e.culprit, e.perf.metric if e.perf else None
    )
    ts = datetime.fromtimestamp(e.ts, UTC)
    title = _title(e)
    culprit = _culprit(e, frames)
    payload: dict[str, Any] = e.model_dump(mode="json")
    payload["frames"] = [f.model_dump() for f in frames]
    payload["raw_frames"] = [f.model_dump() for f in raw_frames] if symbolicated else None
    payload["symbolicated"] = symbolicated
    event = db.get(Event, e.event_id)
    if event is not None:
        return event  # idempotent re-delivery
    event = Event(
        id=e.event_id,
        fingerprint=fp,
        kind=e.kind,
        app=e.app,
        platform=e.platform,
        version=e.version,
        session_id=e.session_id,
        ts=ts,
        title=title,
        culprit=culprit,
        payload=payload,
    )
    db.add(event)
    if e.session_id and db.get(AppSession, e.session_id) is None:
        # Backend events may reference a client session; keep a placeholder so joins work.
        db.add(
            AppSession(
                id=e.session_id,
                app=e.app,
                platform=e.platform,
                version=e.version,
                flags=e.flags,
                os=e.device.os,
                browser=e.device.browser,
                device=e.device.device,
                city=e.device.city,
                locale=e.device.locale,
                started_at=ts,
            )
        )

    group = db.get(Group, fp)
    if group is None:
        group = Group(
            fingerprint=fp,
            app=e.app,
            platform=e.platform,
            kind=e.kind,
            title=title,
            culprit=culprit,
            first_seen=ts,
            last_seen=ts,
            first_version=e.version,
            last_version=e.version,
            count=0,
        )
        db.add(group)
    group.count += 1
    group.last_seen = max(_aware(group.last_seen), ts)
    if version_key(e.version) > version_key(group.last_version):
        group.last_version = e.version
    db.flush()
    _maybe_open_issue(db, group, e, notify)
    return event


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _maybe_open_issue(db: DbSession, group: Group, e: EventIn, notify: Notify | None) -> None:
    if group.status == "resolved":
        if group.resolved_in and version_key(e.version) <= version_key(group.resolved_in):
            return  # old clients still on a pre-fix version
        group.status = "unresolved"
        issue = db.get(Issue, group.issue_id) if group.issue_id else None
        if issue is not None:
            issue.status, issue.reason, issue.version, issue.resolved_at = (
                "open",
                "regression",
                e.version,
                None,
            )
            if notify:
                notify("issue.reopened", issue, group)
        return
    if group.issue_id or group.count < ISSUE_THRESHOLD.get(group.kind, 1):
        return
    seq = (db.scalar(select(func.max(Issue.seq))) or 1000) + 1
    issue = Issue(
        id=f"VIT-{seq}",
        seq=seq,
        fingerprint=group.fingerprint,
        title=group.title,
        kind=group.kind,
        app=group.app,
        status="open",
        reason="new",
        version=e.version,
    )
    db.add(issue)
    group.issue_id = issue.id
    db.flush()
    log.info("issue opened", extra={"issue": issue.id, "fingerprint": group.fingerprint})
    if notify:
        notify("issue.opened", issue, group)


def resolve(db: DbSession, issue: Issue, version: str | None) -> None:
    issue.status, issue.resolved_at = "resolved", datetime.now(UTC)
    group = db.get(Group, issue.fingerprint)
    if group:
        group.status, group.resolved_in = "resolved", version or group.last_version
