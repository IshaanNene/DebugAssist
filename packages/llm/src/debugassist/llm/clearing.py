"""Tool-result clearing (ROADMAP P15 item 3, `DA_CONTEXT=clear`): old tool outputs leave the history in batches.

Every agent turn re-sends the whole history, and the context audit found tool results are most of it. Here,
once the tool output not yet cleared (apart from the newest few results) passes a token threshold, every
result older than those few is replaced by a one-line stub — tool, arguments, size and, when there was one,
the evidence id that claims cite — in one batch.

Why batches: the prompt cache matches the longest identical prefix. Clearing the oldest result every turn
(what a sliding window does) changes the prefix every turn and every turn misses the cache. A boundary that
only moves when the threshold is crossed again rewrites the prefix once per batch; between batches the
prefix is identical and the cache hits. The agent's own state is untouched: only what the model is sent
changes, and the stubs are deterministic, so the same history always produces the same request.
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain.agents.middleware import wrap_model_call
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

# Uncleared tool output (beyond the newest KEEP results) that triggers a batch. Chosen by replaying the
# fix-quality arm's 24 multi-turn agents: 8K fired in 6 (24% of history tokens saved), 4K in 10 (37%),
# 2K in 19 (50%, but a batch — one cache rewrite — every few turns).
TRIGGER_TOKENS = 4_000
KEEP = 3  # the newest tool results always stay whole
MIN_CLEAR_CHARS = 400  # short results are cheaper to keep than to replace with a stub
_EVIDENCE = re.compile(r'"evidence_id":\s*"(ev_[a-z]+_[0-9a-f]{10})"')


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:  # pyright: ignore[reportUnknownVariableType]
            if isinstance(p, dict) and "text" in p:
                parts.append(str(p["text"]))  # pyright: ignore[reportUnknownArgumentType]
            else:
                parts.append(str(p))  # pyright: ignore[reportUnknownArgumentType]
        return "".join(parts)
    return json.dumps(content, default=str)


def tokens(text: str) -> int:
    return len(text) // 4 + 1


def stub(m: ToolMessage, calls: dict[str, tuple[str, dict[str, Any]]]) -> str:
    name, args = calls.get(m.tool_call_id, (m.name or "tool", {}))
    shown = ", ".join(
        f"{k}={str(v)[:50]}" for k, v in args.items() if k not in ("content", "new_text", "old_text")
    )
    text = _text(m.content)
    ev = _EVIDENCE.search(text)
    return (
        f"[cleared: {name}({shown}) returned ~{tokens(text)} tokens"
        + (f", evidence {ev.group(1)}" if ev else "")
        + "; call it again if you need it]"
    )


class Clearing:
    """Per-agent state: how many leading messages have their tool results cleared (only ever grows)."""

    def __init__(self, trigger: int = TRIGGER_TOKENS, keep: int = KEEP) -> None:
        self.trigger, self.keep = trigger, keep
        self.upto = 0  # messages[:upto] have their large tool results stubbed
        self.batches = 0

    def apply(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        tool_idx = [i for i, m in enumerate(messages) if isinstance(m, ToolMessage)]
        if len(tool_idx) > self.keep:
            boundary = tool_idx[-self.keep]  # results from here on stay whole
            pending = sum(
                tokens(_text(messages[i].content))
                for i in tool_idx
                if self.upto <= i < boundary and len(_text(messages[i].content)) >= MIN_CLEAR_CHARS
            )
            if pending >= self.trigger:
                self.upto, self.batches = boundary, self.batches + 1
        if not self.upto:
            return messages
        calls: dict[str, tuple[str, dict[str, Any]]] = {}
        for m in messages:
            if isinstance(m, AIMessage):
                for tc in m.tool_calls:
                    if tc_id := tc.get("id"):
                        calls[tc_id] = (tc["name"], tc.get("args", {}))
        out: list[BaseMessage] = []
        for i, m in enumerate(messages):
            if i < self.upto and isinstance(m, ToolMessage) and len(_text(m.content)) >= MIN_CLEAR_CHARS:
                out.append(m.model_copy(update={"content": stub(m, calls)}))
            else:
                out.append(m)
        return out


def clearing_middleware(state: Clearing) -> Any:
    @wrap_model_call
    async def clear_old_tool_results(request: Any, handler: Any) -> Any:
        return await handler(request.override(messages=state.apply(list(request.messages))))

    return clear_old_tool_results
