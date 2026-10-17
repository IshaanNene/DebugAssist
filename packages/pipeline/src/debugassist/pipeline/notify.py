"""Chat notifications for every pipeline step that pages someone (nodes, post-merge watch, review feedback).

Its own module so those callers share it without importing `nodes` (which imports them): no hidden cycle.
"""

from __future__ import annotations

from typing import Any

import httpx

from debugassist.core.policy import Verdict
from debugassist.integrations.chat import ChatMessage
from debugassist.pipeline.deps import Deps


def notify(deps: Deps, run_id: str, msg: ChatMessage) -> dict[str, Any]:
    """Every chat message goes through the write gate and the audit log (dry-run → not sent)."""
    verdict = deps.gate.verdict("chat.message")
    result: dict[str, Any] = {"to": msg.to, "mode": "dry_run"}
    if verdict is Verdict.LIVE:
        try:
            result = deps.chat.send(msg)
        except httpx.HTTPError as exc:  # a chat outage never fails the run
            result = {"to": msg.to, "mode": deps.chat.mode, "error": f"{type(exc).__name__}: {exc}"[:200]}
    deps.gate.record(
        "chat.message", verdict, run_id=run_id, detail={"to": msg.to, "title": msg.title}, result=result
    )
    return {"kind": "chat", "title": msg.title, **result}
