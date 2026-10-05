from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
    description: Mapped[str] = mapped_column(Text)
    app: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(32))
    session_id: Mapped[str | None] = mapped_column(String(64), index=True)
    analytics_id: Mapped[str | None] = mapped_column(String(64))
    os: Mapped[str | None] = mapped_column(String(64))
    browser: Mapped[str | None] = mapped_column(String(64))
    device: Mapped[str | None] = mapped_column(String(64))
    locale: Mapped[str | None] = mapped_column(String(32))
    city: Mapped[str | None] = mapped_column(String(32))
    route: Mapped[str | None] = mapped_column(String(256))
    flags: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    network: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # captured network profile
    log_counts: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    files: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(
        String(16), default="new"
    )  # new | triaged | in_progress | resolved | duplicate


class ReportLink(Base):
    """Something a report points to: a Jira ticket, a pull request, an RCA report."""

    __tablename__ = "report_links"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(String(16), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # jira | pr | rca | other
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


def make_engine(url: str | None = None) -> Engine:
    return create_engine(
        url or os.environ.get("BUGDROP_DATABASE_URL", "sqlite:///./bugdrop.db"), pool_pre_ping=True
    )


def make_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
