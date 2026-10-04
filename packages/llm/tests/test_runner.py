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
