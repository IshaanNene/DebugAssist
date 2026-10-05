"""Storage: sessions (denominators), events, groups (fingerprints) and issues."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.orm import Session as DbSession


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class AppSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    analytics_id: Mapped[str | None] = mapped_column(String(64))
    app: Mapped[str] = mapped_column(String(64), index=True)
    platform: Mapped[str] = mapped_column(String(16))
    version: Mapped[str] = mapped_column(String(32), index=True)
    os: Mapped[str | None] = mapped_column(String(64))
    browser: Mapped[str | None] = mapped_column(String(64))
    device: Mapped[str | None] = mapped_column(String(64))
    city: Mapped[str | None] = mapped_column(String(32))
    locale: Mapped[str | None] = mapped_column(String(32))
    flags: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    app: Mapped[str] = mapped_column(String(64))
    platform: Mapped[str] = mapped_column(String(16))
    version: Mapped[str] = mapped_column(String(32))
    session_id: Mapped[str | None] = mapped_column(String(64), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    title: Mapped[str] = mapped_column(Text)
    culprit: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class Group(Base):
    __tablename__ = "groups"
    fingerprint: Mapped[str] = mapped_column(String(32), primary_key=True)
    app: Mapped[str] = mapped_column(String(64))
    platform: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(Text)
    culprit: Mapped[str | None] = mapped_column(Text)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    first_version: Mapped[str] = mapped_column(String(32))
    last_version: Mapped[str] = mapped_column(String(32))
    count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="unresolved")  # unresolved | resolved
    resolved_in: Mapped[str | None] = mapped_column(String(32))
    issue_id: Mapped[str | None] = mapped_column(String(16))


class Issue(Base):
    __tablename__ = "issues"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, unique=True)
    fingerprint: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16))
    app: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | resolved
    reason: Mapped[str] = mapped_column(String(16))  # new | regression
    version: Mapped[str] = mapped_column(String(32))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score: Mapped[float] = mapped_column(Float, default=0.0)


class IssueLink(Base):
    """Something an issue points to: a Jira ticket, a pull request, an RCA report."""

    __tablename__ = "issue_links"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_id: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # jira | pr | rca | other
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def make_engine(url: str | None = None) -> Engine:
    url = url or os.environ.get("VITALS_DATABASE_URL", "sqlite:///./vitals.db")
    return create_engine(url, pool_pre_ping=True)


def make_sessionmaker(engine: Engine) -> sessionmaker[DbSession]:
    return sessionmaker(engine, expire_on_commit=False)
