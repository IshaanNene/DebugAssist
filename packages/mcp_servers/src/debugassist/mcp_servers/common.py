"""Shared helpers: result size caps, pagination, evidence IDs, gated writes."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from debugassist.core.evidence import evidence_id
from debugassist.core.redaction import redact

logging.getLogger("httpx").setLevel(logging.WARNING)
MAX_RESULT_CHARS = int(os.environ.get("MCP_MAX_RESULT_CHARS", "12000"))


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def with_evidence(source: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Attach a stable evidence id (cited by RCA claims) and redact PII before anything leaves."""
    clean = redact(payload)
    return {"evidence_id": evidence_id(source, {"kind": kind, "data": clean}), "kind": kind, **clean}


def cap(items: list[Any], limit: int, offset: int = 0) -> dict[str, Any]:
    """Paginate and keep the serialized result under MAX_RESULT_CHARS."""
    page = items[offset : offset + limit]
    out: list[Any] = []
    size = 0
    for it in page:
        size += len(json.dumps(it, default=str))
        if size > MAX_RESULT_CHARS and out:
            break
        out.append(it)
    nxt = offset + len(out)
    return {
        "total": len(items),
        "offset": offset,
        "returned": len(out),
        "next_offset": nxt if nxt < len(items) else None,
        "items": out,
    }


def truncate(text: str, limit: int = MAX_RESULT_CHARS) -> str:
    return (
        text if len(text) <= limit else text[: limit - 60] + f"\n… [truncated {len(text) - limit + 60} chars]"
    )
