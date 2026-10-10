"""Concise tool responses (ROADMAP P15 item 4, `DA_CONTEXT=concise`): smaller tool results, same facts first.

Every tool result is re-sent on every later turn, so its size is paid many times. In this mode a result is
rewritten before the model sees it:
- JSON (every MCP tool returns it, pretty-printed with two-space indents) is re-serialised compactly — the
  whitespace carried no information but cost tokens on every turn;
- lists longer than TOP_K keep their first TOP_K items plus a count of what was left out (MCP tools take
  `offset` / `limit`, so the rest is one call away);
- long text fields are clipped: diffs and file bodies to BLOB characters, other strings inside list items to
  FIELD characters;
- plain-text results (grep) keep their first TEXT_LINES lines and say how many more there were.

Evidence ids and every top-level key are kept, so claims can still cite the result. File reads, command
output and skills are left alone (lean mode covers the first two; skills are instructions, not data). The
evidence store keeps the full result; only what the model is sent changes.

It is a pure function of the tool's name and output, so its effect can be measured offline by replaying
recorded transcripts through it.
"""

from __future__ import annotations

import json
from typing import Any, cast

TOP_K = 10
FIELD = 240
BLOB = 1_500
TEXT_LINES = 30
BLOB_KEYS = {"patch", "diff", "content", "body", "stack", "stacktrace", "text", "log", "logs"}
SKIP = {"read_file", "run_command", "read_log", "load_skill", "outline_file", "submit_result", "list_dir"}
HINT = "narrow the query, or page with offset/limit"


def _shrink(value: Any, *, key: str = "", in_list: bool = False) -> Any:
    if isinstance(value, dict):
        d = cast(dict[str, Any], value)
        return {k: _shrink(v, key=k, in_list=in_list) for k, v in d.items()}
    if isinstance(value, list):
        items = cast(list[Any], value)
        kept = [_shrink(v, key=key, in_list=True) for v in items[:TOP_K]]
        if len(items) > TOP_K:
            kept.append({"omitted": len(items) - TOP_K, "hint": HINT})
        return kept
    if isinstance(value, str):
        limit = BLOB if key in BLOB_KEYS else (FIELD if in_list else None)
        if limit is not None and len(value) > limit:
            return value[:limit] + f"… [{len(value) - limit} more chars]"
    return value


def concise_text(name: str, text: str) -> str:
    if name in SKIP:
        return text
    try:
        data = json.loads(text)
    except ValueError:
        lines = text.splitlines()
        if len(lines) <= TEXT_LINES:
            return text
        return "\n".join(lines[:TEXT_LINES]) + f"\n… [{len(lines) - TEXT_LINES} more lines; {HINT}]"
    return json.dumps(_shrink(data), separators=(",", ":"), ensure_ascii=False, default=str)


def concise(name: str, content: Any) -> Any:
    """A tool message's content (a string, or MCP's list of text blocks), made concise."""
    if isinstance(content, str):
        return concise_text(name, content)
    if isinstance(content, list):
        out: list[Any] = []
        for block in cast(list[Any], content):
            if isinstance(block, dict) and cast(dict[str, Any], block).get("type") == "text":
                b = cast(dict[str, Any], block)
                out.append({**b, "text": concise_text(name, str(b.get("text", "")))})
            else:
                out.append(block)
        return out
    return content
