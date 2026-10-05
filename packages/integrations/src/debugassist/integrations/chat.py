"""Team chat notifications: a Discord channel webhook (free) or a local mock inbox.

Discord: `POST {webhook_url}?wait=true` with `content` (≤ 2,000 chars) and up to 10 `embeds`; 200 with
the created message when `wait=true` (docs.discord.com/developers/resources/webhook, checked 2026-10-05).
Mentions are disabled (`allowed_mentions.parse = []`): people are named, never pinged by accident.
Mock: messages land in .data/mock/chat/inbox.jsonl (the dashboard renders it as an inbox).
Text is PII-redacted before it leaves the machine.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, Field

from debugassist.core.policy import ROOT
from debugassist.core.redaction import redact_text

Level = Literal["info", "success", "warning", "alert"]
COLORS: dict[Level, int] = {"info": 0x5865F2, "success": 0x2EA043, "warning": 0xD29922, "alert": 0xDA3633}


class ChatMessage(BaseModel):
    to: str  # a person ("@priya.nair") or a channel ("#rider-app"), shown in the message
    title: str
    text: str
    level: Level = "info"
    links: dict[str, str] = Field(default_factory=dict[str, str])  # label → URL
    fields: dict[str, str] = Field(default_factory=dict[str, str])  # short facts shown side by side


class Chat(Protocol):
    mode: str

    def send(self, msg: ChatMessage) -> dict[str, Any]: ...


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


class ChatMock:
    mode = "mock"

    def __init__(self, path: Path = ROOT / ".data" / "mock" / "chat" / "inbox.jsonl") -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def send(self, msg: ChatMessage) -> dict[str, Any]:
        entry = {"at": datetime.now(UTC).isoformat(), **msg.model_dump()}
        with self.path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
        return {"to": msg.to, "mode": self.mode}

    def inbox(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text().splitlines()[-limit:]
        return [json.loads(line) for line in reversed(lines)]


class DiscordWebhook:
    mode = "live"

    def __init__(self, url: str, client: httpx.Client | None = None, username: str = "DebugAssist") -> None:
        self.url = url
        self.client = client or httpx.Client(timeout=15)
        self.username = username

    def payload(self, msg: ChatMessage) -> dict[str, Any]:
        links = {k: v for k, v in msg.links.items() if v.startswith(("http://", "https://"))}
        fields = [
            {"name": _clip(k, 256), "value": _clip(redact_text(v), 1024), "inline": True}
            for k, v in msg.fields.items()
            if v
        ]
        if links:
            fields.append(
                {"name": "Links", "value": _clip(" · ".join(f"[{k}]({v})" for k, v in links.items()), 1024)}
            )
        embed: dict[str, Any] = {
            "title": _clip(redact_text(msg.title), 256),
            "description": _clip(redact_text(msg.text), 4000),
            "color": COLORS[msg.level],
            "fields": fields[:25],
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if url := links.get("PR") or next(iter(links.values()), None):
            embed["url"] = url
        return {
            "username": self.username,
            "content": _clip(f"For **{msg.to}**", 2000),
            "embeds": [embed],
            "allowed_mentions": {"parse": []},
        }

    def send(self, msg: ChatMessage) -> dict[str, Any]:
        r = self.client.post(self.url, params={"wait": "true"}, json=self.payload(msg))
        r.raise_for_status()
        body = r.json()
        return {"to": msg.to, "mode": self.mode, "message_id": str(body.get("id", ""))}
