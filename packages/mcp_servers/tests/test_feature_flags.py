from __future__ import annotations

import json
from pathlib import Path

import pytest

from debugassist.core.policy import Policy, PolicyGate, Verdict
from debugassist.mcp_servers.feature_flags import two_proportion_z


def test_crash_rate_difference_is_significant() -> None:
    # The VIT-1001 numbers: 4/8 exposed sessions crashed vs 0/232 unexposed.
    z, p = two_proportion_z(4, 8, 0, 232)
    assert z == pytest.approx(10.86, abs=0.01) and p < 1e-20


def test_equal_rates_are_not_significant() -> None:
    z, p = two_proportion_z(5, 100, 5, 100)
    assert z == 0 and p == pytest.approx(1.0)


def test_empty_groups() -> None:
    assert two_proportion_z(0, 0, 3, 10) == (0.0, 1.0)


def _fake_unleash(monkeypatch: pytest.MonkeyPatch, puts: list[str]) -> None:
    import httpx

    from debugassist.mcp_servers import feature_flags as ff

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "PUT":
            puts.append(json.loads(req.content)["parameters"]["rollout"])
            return httpx.Response(200, json={})
        return httpx.Response(
            200, json=[{"id": "s1", "name": "flexibleRollout", "parameters": {"rollout": "5"}}]
        )

    monkeypatch.setattr(ff, "_http", httpx.Client(transport=httpx.MockTransport(handler)))


def _gate(tmp_path: Path, verdict: str, mode: str = "autonomous") -> PolicyGate:
    return PolicyGate(
        Policy(actions={"flags.rollback": Verdict(verdict)}), tmp_path / "audit.jsonl", mode=mode
    )


def test_an_authorized_rollout_is_applied_and_audited_as_applied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Audit P2-6: the node's decision (a human approval included) is what applies a rollback."""
    from debugassist.mcp_servers.feature_flags import apply_rollout

    puts: list[str] = []
    _fake_unleash(monkeypatch, puts)
    gate = _gate(tmp_path, "approval", mode="supervised")
    assert apply_rollout("f", 0, reason="r", authorized=True, gate=gate, run_id="r1")["applied"] is True
    assert apply_rollout("f", 0, reason="r", authorized=False, gate=gate, run_id="r1")["applied"] is False
    assert puts == ["0"]
    audit = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert [(a["verdict"], a["result"]["applied"]) for a in audit] == [("live", True), ("dry_run", False)]


@pytest.mark.parametrize(("verdict", "mode"), [("approval", "supervised"), ("dry_run", "autonomous")])
def test_the_agent_tool_never_applies_without_a_live_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verdict: str, mode: str
) -> None:
    from debugassist.mcp_servers import feature_flags as ff

    puts: list[str] = []
    _fake_unleash(monkeypatch, puts)
    monkeypatch.setattr(ff, "PolicyGate", lambda mode: _gate(tmp_path, verdict, mode))  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    monkeypatch.setenv("DEBUGASSIST_MODE", mode)
    assert ff.rollback_flag("f", 0, dry_run=False)["applied"] is False and puts == []
