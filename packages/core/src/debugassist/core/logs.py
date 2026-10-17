"""Structured event logs (ROADMAP-100 051): one JSON object per line, per component, under `.data/logs/`.

The console output is for a person watching; these are for a person (or `jq`) looking back at what the poller
and the pipeline did across many runs. Every line carries the time, the component, the event and, inside a run,
its id. Values are redacted like everything else that is stored.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from debugassist.core import runctx
from debugassist.core.policy import ROOT
from debugassist.core.redaction import redact, redact_secrets

LOGS = ROOT / ".data" / "logs"


def event(component: str, name: str, **fields: Any) -> dict[str, Any]:
    """Append one event to `.data/logs/<component>.jsonl`; returns what was written. Never raises."""
    line: dict[str, Any] = {
        "at": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "component": component,
        "event": name,
        **({"run_id": rid} if (rid := runctx.get("DEBUGASSIST_RUN_ID")) else {}),
        **fields,
    }
    line = redact(json.loads(json.dumps(line, default=str)), text=redact_secrets)
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        with (LOGS / f"{component}.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
    except OSError:
        pass  # logging must never take a run down
    return line
