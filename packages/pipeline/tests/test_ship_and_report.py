from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from debugassist.integrations.sandbox import CommandResult
from debugassist.pipeline import nodes, report
from debugassist.pipeline.state import RunState

FIXTURE = Path(__file__).parent / "fixtures" / "run_state.json"


def _state() -> RunState:
    """A trimmed copy of a live VIT-1001 run (validated fix, draft PR)."""
    return RunState.model_validate_json(FIXTURE.read_text())


@dataclass
class FakeEngine:
    action: str
    calls: list[str] = field(default_factory=list[str])

    async def decide(self, decision_id: str, *_: Any, **__: Any) -> Any:
        self.calls.append(decision_id)
        return SimpleNamespace(action=self.action, chosen={"risk": 1.0}, p=0.9, band="act", ledger_id="d1")


async def _ship(state: RunState, action: str) -> str:
    engine = FakeEngine(action)
    out = await nodes.ship_gate(state, SimpleNamespace(engine=engine))  # pyright: ignore[reportArgumentType]
    assert engine.calls == ["D16"]
    return out["ship"].outcome


async def test_validated_fix_follows_clef() -> None:
    assert await _ship(_state(), "open_pr") == "open_pr"


async def test_no_ready_pr_without_validation() -> None:
    s = _state()
    assert s.validation
    s.validation.passed = False
    assert await _ship(s, "open_pr") == "draft_pr"


async def test_no_pr_without_a_verified_reproduction_or_a_source_change() -> None:
    s = _state()
    s.fix_attempts[-1].repro_verified = False
    assert await _ship(s, "open_pr") == "rca_only"
    s = _state()
    s.fix_attempts[-1].files = ["test/router_v2_hydration.test.ts"]  # a test alone is not a fix
    assert await _ship(s, "open_pr") == "rca_only"


@dataclass
class FakeSandbox:
    exit_code: int
    commands: list[str] = field(default_factory=list[str])

    def run(self, command: str, **_: Any) -> CommandResult:
        self.commands.append(command)
        return CommandResult(
            command=command, exit_code=self.exit_code, output="10:41 error 'x' is defined but never used"
        )


def test_ci_checks_gate() -> None:
    comp = {"lint": "pnpm lint && pnpm typecheck"}
    ok, bad = FakeSandbox(0), FakeSandbox(1)
    assert nodes._static_problem(ok, comp, ".") is None  # pyright: ignore[reportPrivateUsage,reportArgumentType]
    problem = nodes._static_problem(bad, comp, ".")  # pyright: ignore[reportPrivateUsage,reportArgumentType]
    assert problem and "run by CI" in problem and "never used" in problem
    assert nodes._static_problem(bad, {}, ".") is None  # pyright: ignore[reportPrivateUsage,reportArgumentType]


def test_report_renders_from_run_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = tmp_path / "runs" / "r1"
    run.mkdir(parents=True)
    (run / "state.json").write_text(FIXTURE.read_text())
    monkeypatch.setattr(report, "RUNS", tmp_path / "runs")

    def nothing(_: object) -> None:
        return None

    def no_decisions(_: object) -> list[dict[str, Any]]:
        return []

    def audit(_: object) -> list[dict[str, Any]]:
        return [{"action": "github.open_pr", "verdict": "live", "detail": {"branch": "b"}}]

    def ci(_: object) -> list[dict[str, Any]]:
        return [{"name": "client", "status": "completed", "conclusion": "success", "url": "u"}]

    monkeypatch.setattr(report, "_decisions", no_decisions)
    monkeypatch.setattr(report, "_audit", audit)
    monkeypatch.setattr(report, "_jira", nothing)
    monkeypatch.setattr(report, "_ci", ci)
    html = report.render("r1")
    assert "TypeError: Cannot read properties of undefined" in html
    assert "await whenHydrated();" in html  # the diff
    assert "client: success" in html and "github.open_pr" in html
    assert "<script" not in html.lower()  # agent text is escaped, never executed


GROQ_TPD = (
    "OpenAIRateLimitError: Error code: 429 - Rate limit reached for model `openai/gpt-oss-120b` on tokens "
    "per day (TPD): Limit 200000, Used 199570, Requested 1487."
)


def test_exhausted_daily_quota_stops_the_run_instead_of_counting_as_a_failed_attempt() -> None:
    from debugassist.llm.spec import LLMResult

    s = _state()
    out_of_quota = LLMResult(
        node="reproduce",
        output=None,
        turns=0,
        status="error",
        error=GROQ_TPD,
        model="m",
        mode="live",
        tool_calls=[],
    )
    with pytest.raises(RuntimeError, match="--resume 20261004-090058-vit-1001 --from-node fix"):
        nodes._stop_if_out_of_quota(out_of_quota, s, "fix")  # pyright: ignore[reportPrivateUsage]
    other = out_of_quota.model_copy(update={"error": "OpenAIInvalidRequestError: 400 bad request"})
    nodes._stop_if_out_of_quota(other, s, "fix")  # pyright: ignore[reportPrivateUsage]


def test_daily_quota_wording_of_both_providers() -> None:
    from debugassist.llm.runner import is_daily_quota

    assert is_daily_quota(GROQ_TPD)
    assert is_daily_quota("Rate limit exceeded: free-models-per-day. Add 10 credits")
    assert not is_daily_quota("on tokens per minute (TPM): Limit 8000, Requested 9388")
    assert not is_daily_quota(None)


def test_reproduction_must_fail_with_the_production_error() -> None:
    issue = _state().issue
    assert issue
    cmd = "pnpm exec vitest run test/x.test.ts"
    real = (
        "Unhandled Rejection\nTypeError: Cannot read properties of undefined (reading 'riderId')\n ❯ routeV2"
    )
    timeout = (
        "× throws when accessing session before hydration completes 5019ms\nError: Test timed out in 5000ms."
    )
    other = "AssertionError: expected 1 to be 2"
    assert nodes._repro_problem(cmd, 1, real, issue) is None  # pyright: ignore[reportPrivateUsage]
    assert "timing out" in (nodes._repro_problem(cmd, 1, timeout, issue) or "")  # pyright: ignore[reportPrivateUsage]
    assert "reported error" in (nodes._repro_problem(cmd, 1, other, issue) or "")  # pyright: ignore[reportPrivateUsage]
    assert "passes" in (nodes._repro_problem(cmd, 0, real, issue) or "")  # pyright: ignore[reportPrivateUsage]
    assert nodes._error_signature(issue) == "Cannot read properties of undefined (reading 'riderId')"  # pyright: ignore[reportPrivateUsage]
