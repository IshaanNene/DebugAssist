from __future__ import annotations

import json
from pathlib import Path

import pytest

from debugassist.core import openrouter


def test_model_info_reads_capabilities_and_prices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = tmp_path / "models.json"
    cache.write_text(
        json.dumps(
            [
                {
                    "id": "a/paid",
                    "supported_parameters": ["tools", "structured_outputs"],
                    "pricing": {"prompt": "0.00000015", "completion": "0.0000006"},
                    "context_length": 131072,
                },
                {
                    "id": "b/free:free",
                    "supported_parameters": ["tools"],
                    "pricing": {"prompt": "0", "completion": "0"},
                },
            ]
        )
    )
    monkeypatch.setattr(openrouter, "CACHE", cache)
    monkeypatch.setattr(openrouter, "_catalog", lambda: json.loads(cache.read_text()))
    openrouter.model_info.cache_clear()
    paid = openrouter.model_info("a/paid")
    assert paid.structured_outputs and not paid.free
    assert paid.price_in_per_mtok == pytest.approx(0.15) and paid.price_out_per_mtok == pytest.approx(0.6)
    free = openrouter.model_info("b/free:free")
    assert free.free and not free.structured_outputs
    unknown = openrouter.model_info("c/unknown")
    assert unknown.supported_parameters == ["tools", "max_tokens"] and not unknown.structured_outputs
    openrouter.model_info.cache_clear()


def test_structured_outputs_override_falls_back_to_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    from debugassist.core.llm_models import model_info
    from debugassist.core.settings import get_settings

    monkeypatch.setenv("LLM_STRUCTURED_OUTPUTS", "false")
    get_settings.cache_clear()
    try:
        info = model_info("openai/gpt-oss-120b", "groq")
        assert not info.structured_outputs
        assert "tools" in info.supported_parameters
    finally:
        monkeypatch.delenv("LLM_STRUCTURED_OUTPUTS")
        get_settings.cache_clear()
