"""Decision ledger: one row per decision call (Clef, LLM baseline, local or mock).

Rows hold what is needed to audit, evaluate and recalibrate a decision later: the template
version, the exact compact state (and its hash), the questions sent, every probability returned,
the policy band and action taken, latency, tokens, cost, run mode, and — once known — the outcome
label. SQLite in dev and tests, Postgres in the compose stack (same schema).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


class DecisionRow(Base):
    __tablename__ = "decision_ledger"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    run_id: Mapped[str | None] = mapped_column(String(64), index=True)
    issue_id: Mapped[str | None] = mapped_column(String(64), index=True)
    parent_id: Mapped[str | None] = mapped_column(String(36))  # second opinion → first decision
    decision_id: Mapped[str] = mapped_column(String(64), index=True)
    template_version: Mapped[int] = mapped_column(Integer)
    backend: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(8))
    state: Mapped[Any] = mapped_column(JSON)
    state_hash: Mapped[str] = mapped_column(String(64), index=True)
    questions: Mapped[Any] = mapped_column(JSON)
    n_images: Mapped[int] = mapped_column(Integer, default=0)
    answers: Mapped[Any] = mapped_column(JSON)
    chosen: Mapped[Any] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float)
    band: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(64))
    latency_ms: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float)
    n_calls: Mapped[int] = mapped_column(Integer, default=1)
    fallback_reason: Mapped[str | None] = mapped_column(Text)
    outcome_label: Mapped[Any | None] = mapped_column(JSON)
    outcome_source: Mapped[str | None] = mapped_column(String(32))
    labeled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Ledger:
    """Async writer/reader for the decision ledger."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)

    @classmethod
    async def open(cls, url: str) -> Ledger:
        if url.startswith("sqlite") and ":///" in url and ":memory:" not in url:
            Path(url.split(":///", 1)[1]).parent.mkdir(parents=True, exist_ok=True)
        ledger = cls(create_async_engine(url))
        async with ledger._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return ledger

    async def close(self) -> None:
        await self._engine.dispose()

    async def record(self, row: DecisionRow) -> str:
        async with self._sessions() as session, session.begin():
            session.add(row)
        return row.id

    async def get(self, row_id: str) -> DecisionRow | None:
        async with self._sessions() as session:
            return await session.get(DecisionRow, row_id)

    async def list(self, *, decision_id: str | None = None, run_id: str | None = None) -> list[DecisionRow]:
        stmt = select(DecisionRow).order_by(DecisionRow.created_at)
        if decision_id is not None:
            stmt = stmt.where(DecisionRow.decision_id == decision_id)
        if run_id is not None:
            stmt = stmt.where(DecisionRow.run_id == run_id)
        async with self._sessions() as session:
            return list((await session.scalars(stmt)).all())

    async def label(self, row_id: str, outcome: Any, *, source: str) -> None:
        async with self._sessions() as session, session.begin():
            await session.execute(
                update(DecisionRow)
                .where(DecisionRow.id == row_id)
                .values(outcome_label=outcome, outcome_source=source, labeled_at=datetime.now(UTC))
            )
