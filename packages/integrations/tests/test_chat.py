from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from debugassist.integrations.chat import ChatMessage, ChatMock, DiscordWebhook


def msg() -> ChatMessage:
    return ChatMessage(
        to="@priya.nair",
        title="Fix ready: crash for jo@example.com",
        text="Root cause found. Call +1 415 555 0100 for details.",
        level="success",
        links={"PR": "https://github.com/o/r/pull/7", "Jira": "", "Vitals issue": "mock://vitals/VIT-1"},
        fields={"Outcome": "open_pr", "Empty": ""},
    )


def test_discord_payload_redacts_disables_mentions_and_keeps_real_links() -> None:
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"id": "123"})

    hook = DiscordWebhook(
        "https://discord.com/api/webhooks/1/tok", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    out = hook.send(msg())
    assert out == {"to": "@priya.nair", "mode": "live", "message_id": "123"}
    assert str(seen["url"]).endswith("?wait=true")
    body: dict[str, Any] = seen["body"]
    embed: dict[str, Any] = body["embeds"][0]
    assert body["allowed_mentions"] == {"parse": []} and "priya.nair" in body["content"]
    assert "jo@example.com" not in embed["title"] and "555" not in embed["description"]
    assert embed["url"] == "https://github.com/o/r/pull/7"
    fields: list[dict[str, Any]] = embed["fields"]
    names = [f["name"] for f in fields]
    assert names == ["Outcome", "Links"]  # empty fields dropped
    assert (
        "mock://" not in embed["fields"][-1]["value"]
        and "[PR](https://github.com/o/r/pull/7)" in embed["fields"][-1]["value"]
    )


def test_long_text_is_clipped_to_discord_limits() -> None:
    long = ChatMessage(to="#x", title="t" * 400, text="d" * 5000)
    embed = DiscordWebhook("https://x").payload(long)["embeds"][0]
    assert len(embed["title"]) == 256 and len(embed["description"]) == 4000


def test_mock_inbox_keeps_messages_newest_first(tmp_path: Path) -> None:
    inbox = ChatMock(tmp_path / "inbox.jsonl")
    inbox.send(msg())
    inbox.send(ChatMessage(to="#rider-app", title="second", text="x"))
    got = inbox.inbox()
    assert [m["title"] for m in got] == ["second", "Fix ready: crash for jo@example.com"]
    assert inbox.send(msg()) == {"to": "@priya.nair", "mode": "mock"}


def test_discord_waits_out_a_rate_limit_and_reads_the_message_id() -> None:
    """ROADMAP-100 078, against Discord's documented responses (fixtures/discord/README.md: not recorded live)."""
    import json
    from pathlib import Path

    import httpx

    fx = Path(__file__).parent / "fixtures" / "discord"
    replies = [
        httpx.Response(
            429, json=json.loads((fx / "rate_limited.json").read_text()), headers={"retry-after": "1"}
        ),
        httpx.Response(200, json=json.loads((fx / "message.json").read_text())),
    ]
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return replies.pop(0)

    waits: list[float] = []
    hook = DiscordWebhook(
        "https://discord.com/api/webhooks/1/x",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=waits.append,
    )
    out = hook.send(ChatMessage(to="@oncall", title="Fix ready for review", text="t"))
    assert out == {"to": "@oncall", "mode": "live", "message_id": "1290000000000000001"}
    assert waits == [0.25] and len(seen) == 2 and seen[0].url.params["wait"] == "true"
