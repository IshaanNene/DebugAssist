from typing import Any

import pytest
from typer.testing import CliRunner

from debugassist.decisions.backends.llm import LLMDecider
from debugassist.decisions.schema import ClefRequest, ClefTransientError


class FakeUsage:
    input_tokens = 100
    output_tokens = 20
    input_tokens_total = 100
    output_tokens_total = 20


class FakeResult:
    usage = FakeUsage()

    def __init__(self, answers: dict[str, Any]) -> None:
        self._answers = answers

    def model_dump(self, mode: str = "python") -> dict[str, Any]:
        return {"answers": self._answers}


def decider() -> LLMDecider:
    return LLMDecider(
        model="openai/gpt-oss-120b",
        base_url="https://openrouter.ai/api/v1",
        api_key="k",
        provider_order=["groq"],
        price_in_per_mtok=0.15,
        price_out_per_mtok=0.75,
    )


async def test_llm_decider_converts_adapter_output(
    monkeypatch: pytest.MonkeyPatch, basic_questions: dict[str, Any]
) -> None:
    d = decider()
    answers = {
        "needs_code_change": {"type": "noul", "noul": 0.9},
        "category": {
            "type": "choice",
            "choice": "own_code",
            "confidence": 0.8,
            "probabilities": {"own_code": 0.8, "third_party": 0.1, "infra": 0.05, "network": 0.05},
        },
        "severity": {
            "type": "score",
            "score": 2.6,
            "confidence": 0.6,
            "legend": {"0": "cosmetic", "1": "minor", "2": "major", "3": "crash"},
            "probabilities": {"0": 0.0, "1": 0.1, "2": 0.2, "3": 0.7},
        },
    }

    async def fake(state: Any, questions: Any) -> FakeResult:
        return FakeResult(answers)

    monkeypatch.setattr(d._client, "system_one", fake)  # pyright: ignore[reportPrivateUsage]
    req = ClefRequest.model_validate(
        {
            "model": "clef",
            "state": "s",
            "questions": basic_questions,
            "images": ["data:image/png;base64,AA=="],
        }
    )
    resp = await d.run(req)
    assert resp.model == "openai/gpt-oss-120b"
    assert d.cost_usd(resp) == pytest.approx((100 * 0.15 + 20 * 0.75) / 1e6)
    assert d.last_note and "text-only" in d.last_note
    await d.aclose()


async def test_llm_decider_wraps_adapter_errors(
    monkeypatch: pytest.MonkeyPatch, basic_questions: dict[str, Any]
) -> None:
    from typesafe_sdk import TypeSafeError

    d = decider()

    async def boom(state: Any, questions: Any) -> None:
        raise TypeSafeError("malformed")

    monkeypatch.setattr(d._client, "system_one", boom)  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(ClefTransientError):
        await d.run(ClefRequest.model_validate({"model": "clef", "state": "s", "questions": basic_questions}))


def test_cli_decide_in_mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from debugassist.core.settings import get_settings
    from debugassist.decisions.cli import app

    monkeypatch.setenv("DA_MODE_CLEF", "mock")
    monkeypatch.setenv("DA_MODE_LLM", "mock")
    get_settings.cache_clear()
    runner = CliRunner()
    out = runner.invoke(app, ["decide", "D11", "--state", '{"flag":"x"}', "--no-ledger", "--json"])
    assert out.exit_code == 0, out.output
    assert '"decision_id": "D11_mitigation"' in out.output and '"mode": "mock"' in out.output
    human = runner.invoke(app, ["decide", "D05", "--state", '{"e":"boom"}', "--no-ledger"])
    assert human.exit_code == 0 and "policy:" in human.output
    assert runner.invoke(app, ["templates"]).exit_code == 0
    get_settings.cache_clear()
