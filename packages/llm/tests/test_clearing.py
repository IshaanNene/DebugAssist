from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from debugassist.llm.clearing import Clearing


def _step(i: int, size: int = 4_000, ev: bool = False) -> list[BaseMessage]:
    head = f'{{"evidence_id": "ev_code_{i:010x}", ' if ev else "{"
    body = head + '"content": "' + "x" * size + '"}'
    call = {"id": f"c{i}", "name": "read_file", "args": {"path": f"src/f{i}.ts", "start_line": 1}}
    return [AIMessage(content="", tool_calls=[call]), ToolMessage(content=body, tool_call_id=f"c{i}")]


def _history(n: int, size: int = 4_000, ev: bool = False) -> list[BaseMessage]:
    out: list[BaseMessage] = [HumanMessage("task")]
    for i in range(n):
        out += _step(i, size=size, ev=ev)
    return out


def _cleared(msgs: list[BaseMessage]) -> list[int]:
    return [
        i for i, m in enumerate(msgs) if isinstance(m, ToolMessage) and str(m.content).startswith("[cleared")
    ]


def test_nothing_is_cleared_below_the_threshold() -> None:
    c = Clearing(trigger=8_000, keep=3)
    msgs = _history(4)  # one result beyond the newest three: ~1K tokens
    assert c.apply(msgs) == msgs and c.batches == 0


def test_a_batch_clears_everything_but_the_newest_results() -> None:
    c = Clearing(trigger=3_000, keep=3)
    out = c.apply(_history(8, ev=True))
    tools = [m for m in out if isinstance(m, ToolMessage)]
    assert c.batches == 1
    assert all(str(m.content).startswith("[cleared: read_file(path=src/f") for m in tools[:5])
    assert all(not str(m.content).startswith("[cleared") for m in tools[5:])
    # the evidence id survives, so claims can still cite it
    assert "evidence ev_code_0000000000" in str(tools[0].content)


def test_the_boundary_is_sticky_so_the_prefix_stays_identical() -> None:
    c = Clearing(trigger=3_000, keep=3)
    hist = _history(8)
    first = c.apply(hist)
    # two more turns, below the threshold again: the earlier part of the request must not change
    hist2 = hist + _step(8) + _step(9)
    second = c.apply(hist2)
    assert c.batches == 1
    assert [m.content for m in second[: len(first)]] == [m.content for m in first]
    assert _cleared(second) == _cleared(first)


def test_the_boundary_moves_only_once_enough_new_output_piles_up() -> None:
    c = Clearing(trigger=3_000, keep=3)
    hist = _history(8)
    c.apply(hist)
    seen: list[int] = []
    for i in range(8, 14):  # each step adds ~1K tokens: a new batch every third step, not every step
        hist = hist + _step(i)
        c.apply(hist)
        seen.append(c.batches)
    assert seen == [1, 1, 2, 2, 2, 3]


def test_short_results_and_the_agents_state_are_left_alone() -> None:
    c = Clearing(trigger=1, keep=1)
    hist = _history(3, size=50)  # tiny results: not worth a stub
    assert c.apply(hist) == hist
    big = _history(4)
    before = [m.content for m in big]
    c2 = Clearing(trigger=1_000, keep=1)
    c2.apply(big)
    assert [m.content for m in big] == before  # only the request changes, never the history itself
