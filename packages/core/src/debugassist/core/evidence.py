"""Evidence items with stable, content-derived IDs that RCA claims cite."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from debugassist.core.ledger import canonical_json

Source = Literal[
    "vitals",
    "bugdrop",
    "logs",
    "traces",
    "metrics",
    "flags",
    "releases",
    "git",
    "code",
    "incident",
    "screenshot",
    "jira",
]


def evidence_id(source: str, payload: Any) -> str:
    return f"ev_{source}_{hashlib.sha1(canonical_json(payload).encode()).hexdigest()[:10]}"  # noqa: S324 - id, not security


class EvidenceItem(BaseModel):
    id: str
    source: Source
    kind: str  # e.g. crash_event, flag_exposure, commit, file_excerpt
    summary: str
    ts: datetime | None = None
    data: dict[str, Any] = Field(default_factory=dict[str, Any])

    @classmethod
    def make(
        cls, source: Source, kind: str, summary: str, data: dict[str, Any], ts: datetime | None = None
    ) -> EvidenceItem:
        return cls(
            id=evidence_id(source, {"kind": kind, "data": data}),
            source=source,
            kind=kind,
            summary=summary,
            ts=ts,
            data=data,
        )
