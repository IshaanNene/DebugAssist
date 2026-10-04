"""Slack: a local mock inbox (no workspace configured). Messages land in .data/mock/slack/inbox.jsonl."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from debugassist.core.policy import ROOT


class SlackMock:
    def __init__(self, path: Path = ROOT / ".data" / "mock" / "slack" / "inbox.jsonl") -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def message(self, to: str, text: str, links: dict[str, str] | None = None) -> dict[str, str]:
        entry = {"at": datetime.now(UTC).isoformat(), "to": to, "text": text, "links": links or {}}
        with self.path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
        return {"channel": to, "mode": "mock"}
