# pyright: reportPrivateUsage=false
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import openai
import pytest
from pydantic import BaseModel

from debugassist.llm.runner import CassetteRunner, ScriptedRunner, _text, _transient
from debugassist.llm.spec import LLMNodeSpec


class Out(BaseModel):
    answer: str


def _status_error(code: int, message: str) -> openai.APIStatusError:
    req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    resp: Any = httpx.Response(code, request=req)
    return openai.APIStatusError(message, response=resp, body=None)


def test_transient_errors_are_retried_but_daily_quota_is_not() -> None:
    assert _transient(TimeoutError())
    assert _transient(_status_error(503, "Upstream error from Nvidia: Service temporarily overloaded"))
    assert _transient(_status_error(429, "Rate limit exceeded: 20 per minute"))
    assert not _transient(_status_error(429, "Rate limit exceeded: free-models-per-day"))
    assert not _transient(_status_error(400, "bad request"))


def test_text_of_content_blocks() -> None:
    assert _text("plain") == "plain"
    assert _text([{"type": "text", "text": "a"}, "b"]) == "a b"
    assert _text(None) == ""


def _spec() -> LLMNodeSpec:
    return LLMNodeSpec(node="fix", system_prompt="s", model="test/model")


async def test_scripted_runner_is_labelled_mock_and_applies_patch(tmp_path: Path) -> None:
    (tmp_path / "fix.json").write_text(
        json.dumps({"output": {"answer": "42"}, "tool_calls": [{"name": "read_file"}]})
    )
    (tmp_path / "fix.patch").write_text("diff --git a/x b/x\n")
    applied: list[str] = []
    r = await ScriptedRunner(tmp_path, applied.append).run(_spec(), "p", Out)
    assert r.mode == "mock" and r.model == "scripted" and r.output == {"answer": "42"}
    assert applied == ["diff --git a/x b/x\n"] and r.tool_calls[0].name == "read_file"


async def test_scripted_runner_validates_output(tmp_path: Path) -> None:
    (tmp_path / "fix.json").write_text(json.dumps({"output": {"wrong": 1}}))
    with pytest.raises(ValueError):
        await ScriptedRunner(tmp_path).run(_spec(), "p", Out)


async def test_cassette_replay_is_labelled_replay(tmp_path: Path) -> None:
    live: dict[str, Any] = {
        "node": "fix",
        "output": {"answer": "x"},
        "status": "ok",
        "turns": 3,
        "model": "m",
        "mode": "live",
        "tool_calls": [],
    }
    (tmp_path / "fix.json").write_text(json.dumps({"result": live, "transcript": []}))
    r = await CassetteRunner(tmp_path).run(_spec(), "p", Out)
    assert r.mode == "replay" and r.output == {"answer": "x"} and r.turns == 3


def _steps(n: int, tool_chars: int) -> list[Any]:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    msgs: list[Any] = [HumanMessage("TASK " + "x" * 300)]
    for i in range(n):
        msgs.append(
            AIMessage("", tool_calls=[{"name": "read_file", "args": {"path": f"f{i}"}, "id": f"c{i}"}])
        )
        msgs.append(ToolMessage("y" * tool_chars, tool_call_id=f"c{i}"))
    return msgs


def test_budget_keeps_small_conversations_unchanged() -> None:
    from debugassist.llm.runner import fit_to_budget

    msgs = _steps(2, 100)
    assert fit_to_budget(msgs, 10_000) == msgs


def test_budget_keeps_task_and_newest_steps_and_pairs() -> None:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from debugassist.llm.runner import approx_tokens, fit_to_budget

    msgs = _steps(12, 3_000)
    out = fit_to_budget(msgs, 2_500)
    assert out[0] is msgs[0] and isinstance(out[1], HumanMessage) and "omitted" in str(out[1].content)
    assert sum(approx_tokens(m.content) for m in out) <= 2_500 + 200
    tail = out[2:]
    assert isinstance(tail[0], AIMessage) and isinstance(tail[-1], ToolMessage)
    ids = [tc["id"] for m in tail if isinstance(m, AIMessage) for tc in m.tool_calls]
    assert [
        m.tool_call_id for m in tail if isinstance(m, ToolMessage)
    ] == ids  # calls and results stay paired
    assert ids[-1] == "c11"  # the newest step is always kept


def test_budget_clips_an_oversized_newest_step() -> None:
    from debugassist.llm.runner import fit_to_budget

    out = fit_to_budget(_steps(1, 60_000), 3_000)
    assert "clipped to fit the context budget" in str(out[-1].content)


async def test_unknown_tool_rejection_is_retried_with_the_real_tool_names() -> None:
    from dataclasses import dataclass, replace

    from debugassist.llm.runner import recover_unknown_tool

    @dataclass
    class Req:
        messages: list[Any]
        tools: list[Any]

        def override(self, **kw: Any) -> Req:
            return replace(self, **kw)

    seen: list[Req] = []

    async def handler(req: Req) -> str:
        seen.append(req)
        if len(seen) == 1:
            raise openai.BadRequestError(
                "tool call validation failed (tool_use_failed): attempted to call tool 'search'",
                response=_status_error(400, "x").response,
                body=None,
            )
        return "ok"

    tools = [type("T", (), {"name": "grep"})(), type("T", (), {"name": "read_file"})()]
    out = await recover_unknown_tool.awrap_model_call(Req(["task"], tools), handler)  # pyright: ignore[reportArgumentType]
    assert out == "ok" and len(seen) == 2
    assert "Only these tools exist: grep, read_file" in str(seen[1].messages[-1].content)
