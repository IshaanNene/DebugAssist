"""Sanity checks on live Workers AI fixtures recorded 2026-10-04 (full conformance suite lands in P1)."""

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "workers_ai"


@pytest.mark.parametrize("model", ["clef", "clef-flash"])
def test_live_fixture_uses_cloudflare_envelope(model: str) -> None:
    raw = json.loads((FIXTURES / f"{model}_basic.json").read_text())
    assert raw["success"] is True and raw["errors"] == []
    result = raw["result"]
    assert result["model"] == model
    assert result["usage"]["output_tokens"] == 0
    answers = result["answers"]
    assert answers["needs_code_change"]["type"] == "noul"
    assert 0.0 <= answers["needs_code_change"]["noul"] <= 1.0
    probs = answers["category"]["probabilities"]
    assert abs(sum(probs.values()) - 1.0) < 1e-3
    assert answers["category"]["choice"] == max(probs, key=probs.__getitem__)
    assert set(answers["severity"]["legend"]) == {"0", "1", "2", "3"}
