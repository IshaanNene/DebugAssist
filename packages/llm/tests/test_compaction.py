from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from debugassist.llm.compaction import Compaction, render


class FakeModel:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        self.prompts.append(str(messages[-1].content))
        n = len(self.prompts)
        return AIMessage(
            content=f"Goal: fix the ETA\nFindings: - ev_code_000000000{n} matching.py:96 (notes v{n})",
            usage_metadata={"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100},
        )


def _step(i: int, size: int = 4_000) -> list[BaseMessage]:
    call = {"id": f"c{i}", "name": "read_file", "args": {"path": f"src/f{i}.py"}}
    return [
        AIMessage(content=f"look at f{i}", tool_calls=[call]),
        ToolMessage(content="x" * size, tool_call_id=f"c{i}"),
    ]


def _history(n: int) -> list[BaseMessage]:
    out: list[BaseMessage] = [HumanMessage("task: the ETA is wrong")]
    for i in range(n):
        out += _step(i)
    return out


def _run(c: Compaction, msgs: list[BaseMessage], model: Any) -> list[BaseMessage]:
    return asyncio.run(c.apply(msgs, model))


def test_below_the_threshold_nothing_changes() -> None:
    c, m = Compaction(trigger=6_000, keep=2), FakeModel()
    msgs = _history(3)  # ~3K tokens of history
    assert _run(c, msgs, m) == msgs and not m.prompts


def test_old_steps_fold_into_notes_and_the_newest_stay() -> None:
    c, m = Compaction(trigger=3_000, keep=2), FakeModel()
    out = _run(c, _history(6), m)
    assert c.compactions == 1 and len(m.prompts) == 1
    assert out[0].content == "task: the ETA is wrong"
    assert "Working notes" in str(out[1].content) and "notes v1" in str(out[1].content)
    assert [str(x.content) for x in out[2:] if isinstance(x, AIMessage)] == ["look at f4", "look at f5"]
    # the summariser saw the folded steps, with tool output fenced as untrusted data
    assert "CALL read_file" in m.prompts[0] and "untrusted_data" in m.prompts[0]
    assert (c.input_tokens, c.output_tokens) == (1000, 100)


def test_the_prefix_is_stable_until_the_next_compaction() -> None:
    c, m = Compaction(trigger=3_000, keep=2), FakeModel()
    hist = _history(6)
    first = _run(c, hist, m)
    hist2 = hist + _step(6, size=200)  # a small step: still under the threshold
    second = _run(c, hist2, m)
    assert c.compactions == 1
    assert [x.content for x in second[: len(first)]] == [x.content for x in first]


def test_a_second_compaction_folds_the_previous_notes() -> None:
    c, m = Compaction(trigger=3_000, keep=2), FakeModel()
    hist = _history(6)
    _run(c, hist, m)
    for i in range(6, 10):
        hist = hist + _step(i)
    out = _run(c, hist, m)
    assert c.compactions == 2 and "Earlier notes:" in m.prompts[1] and "notes v1" in m.prompts[1]
    assert "notes v2" in str(out[1].content)


def test_render_keeps_identifiers() -> None:
    text = render(_step(3, size=10))
    assert "src/f3.py" in text and "RESULT read_file" in text


def test_a_large_recent_step_does_not_retrigger_every_turn() -> None:
    """Regression: the newest steps (kept whole) counted toward the trigger, so a compaction fired each turn."""
    c, m = Compaction(trigger=3_000, keep=2), FakeModel()
    hist = _history(6)
    _run(c, hist, m)
    assert c.compactions == 1
    for i in range(6, 8):  # each new step is big, but only one step at a time becomes foldable
        hist = hist + _step(i, size=6_000)
        _run(c, hist, m)
    assert c.compactions == 1
