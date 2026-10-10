"""Compaction with notes (ROADMAP P15 item 7, `DA_CONTEXT=compact`): older steps fold into structured notes.

When the history after the task (and after any earlier notes) passes a token threshold, every step but the
newest few is summarised by the same model into working notes — goal, findings with evidence ids and
file:line, hypotheses and what was ruled out, changes made, commands and their outcomes, next step — and the
model is then sent: the task, the notes, the newest steps. Later compactions fold the previous notes and the
newly old steps into new notes.

Like clearing, the boundary only moves when the threshold is crossed again, so the request prefix (task +
notes) is identical between compactions and the prompt cache keeps hitting. Unlike clearing, the model keeps
a digest of what it learnt instead of stubs it must re-fetch — at the cost of one extra model call per
compaction, whose tokens are counted in the agent's cost and logged as a `compact` event.

The agent's own state is untouched: only what the model is sent changes. Tool output stays inside an
untrusted-data fence for the summariser too.
"""

from __future__ import annotations

import json
from typing import Any, cast

from langchain.agents.middleware import wrap_model_call
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from debugassist.core import untrusted
from debugassist.llm.clearing import _text, tokens  # pyright: ignore[reportPrivateUsage]

# History after the task/notes that triggers a compaction. Chosen by replaying the fix-quality arm's 24
# multi-turn agents: 5K fires in 10 (as often as clearing's 4K, for a fair comparison), 4K in 16, 6K in 6.
TRIGGER_TOKENS = 5_000
KEEP_STEPS = 2  # the newest steps (an AI message and its tool results) always stay whole
TOOL_CHARS = 3_000  # per tool result, in what the summariser reads

NOTES_PROMPT = """You keep the working notes of an engineer debugging a production issue. Fold the earlier notes
(if any) and the steps below into new notes. Keep every exact identifier the work may need again: evidence ids
(ev_…), file paths with line numbers, function names, test names, commands, error messages. Drop what was
merely looked at and turned out irrelevant, except to list it under "Ruled out". Be terse; at most 350 words.

Format:
Goal: …
Findings: - … (evidence id / file:line)
Hypotheses: - … (open | confirmed | rejected)
Ruled out: - …
Changes made: - file — what changed (or "none")
Commands and outcomes: - `cmd` → result
Next step: …"""


def render(steps: list[BaseMessage]) -> str:
    """The steps as plain text for the summariser (tool output clipped and fenced as untrusted data)."""
    lines: list[str] = []
    names: dict[str, str] = {}
    for m in steps:
        if isinstance(m, AIMessage):
            said = _text(m.content).strip()
            if said:
                lines.append(f"ENGINEER: {said[:800]}")
            for tc in m.tool_calls:
                names[tc.get("id") or ""] = tc["name"]
                lines.append(f"CALL {tc['name']}({json.dumps(tc.get('args', {}), default=str)[:300]})")
        elif isinstance(m, ToolMessage):
            name = names.get(m.tool_call_id, m.name or "tool")
            lines.append(f"RESULT {name}:\n" + untrusted.fence(name, _text(m.content)[:TOOL_CHARS]))
    return "\n".join(lines)


class Compaction:
    """Per-agent state: the current notes and how many leading messages they replace (only ever grows)."""

    def __init__(self, trigger: int = TRIGGER_TOKENS, keep: int = KEEP_STEPS) -> None:
        self.trigger, self.keep = trigger, keep
        self.notes = ""
        self.upto = 0  # messages[1:upto] are folded into the notes (0: nothing yet)
        self.compactions = 0
        self.input_tokens = self.output_tokens = self.cached_tokens = 0

    def boundary(self, messages: list[BaseMessage]) -> int | None:
        """Where to cut (an AI message index) if the uncompacted history is over the threshold, else None."""
        start = self.upto or 1
        rest = messages[start:]
        if sum(tokens(_text(m.content)) for m in rest) < self.trigger:
            return None
        ai = [start + i for i, m in enumerate(rest) if isinstance(m, AIMessage)]
        if len(ai) <= self.keep:
            return None
        return ai[-self.keep]

    def view(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        if not self.upto:
            return messages
        note = HumanMessage(
            "[Working notes — earlier steps of this task, compacted. Re-run a tool if you need exact output.]\n"
            + self.notes
        )
        return [messages[0], note, *messages[self.upto :]]

    async def apply(self, messages: list[BaseMessage], model: Any) -> list[BaseMessage]:
        cut = self.boundary(messages)
        if cut is not None:
            folded = messages[(self.upto or 1) : cut]
            prompt = (f"Earlier notes:\n{self.notes}\n\n" if self.notes else "") + "Steps:\n" + render(folded)
            reply = await model.ainvoke([SystemMessage(NOTES_PROMPT), HumanMessage(prompt)])
            usage = cast(dict[str, Any], getattr(reply, "usage_metadata", None) or {})
            details = cast(dict[str, Any], usage.get("input_token_details") or {})
            self.input_tokens += int(usage.get("input_tokens", 0))
            self.output_tokens += int(usage.get("output_tokens", 0))
            self.cached_tokens += int(details.get("cache_read") or 0)
            self.notes = _text(reply.content).strip()[:4_000]
            self.upto, self.compactions = cut, self.compactions + 1
        return self.view(messages)


def compaction_middleware(state: Compaction, on_compact: Any = None) -> Any:
    @wrap_model_call
    async def compact_history(request: Any, handler: Any) -> Any:
        before = state.compactions
        messages = await state.apply(list(request.messages), request.model)
        if on_compact is not None and state.compactions > before:
            on_compact(state)
        return await handler(request.override(messages=messages))

    return compact_history
