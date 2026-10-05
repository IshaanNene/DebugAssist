from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from debugassist.decisions.policy import Band
from debugassist.integrations.sandbox import Sandbox
from debugassist.pipeline import e2e, fixplan, nodes
from debugassist.pipeline.state import (
    RCA,
    Claim,
    CodeLocation,
    FixPlan,
    Issue,
    Mitigation,
    RCAOutput,
    RunState,
)

POLLER_V1 = """\
export class EtaPoller {
  private last = { at: 0 };
  start() {
    this.schedule(0);
  }
  private nextDelay(): number {
    return 1000;
  }
  private refreshLocally() {
    this.emit();
  }
}
"""
POLLER_V2 = POLLER_V1.replace("return 1000;", "return this.last.at + 1000 - Date.now();")
SCREEN = """\
import { EtaPoller } from "../eta/poller";
export function RideScreen() {
  const poller = new EtaPoller();
  const prefill = (window.history.state as { x?: number } | null)?.x ?? null;
  return [poller, prefill];
}
"""


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=repo, check=True, capture_output=True
    )


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Sandbox:
    repo = tmp_path / "repo"
    (repo / "src" / "eta").mkdir(parents=True)
    (repo / "src" / "screens").mkdir()
    git(repo, "init", "-q")
    (repo / "src" / "eta" / "poller.ts").write_text(POLLER_V1)
    (repo / "src" / "screens" / "RideScreen.tsx").write_text(SCREEN)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "feat: poller")
    git(repo, "tag", "v1.5.2")
    (repo / "src" / "eta" / "poller.ts").write_text(POLLER_V2)
    git(repo, "commit", "-qam", "refactor(eta): schedule ticks from the last refresh")
    git(repo, "tag", "v1.6.0")
    sb = Sandbox(run_id="r", repo_path=repo, repo="o/r")
    monkeypatch.setattr(Sandbox, "worktree", property(lambda self: repo))  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    return sb


def issue(**kw: Any) -> Issue:
    base: dict[str, Any] = dict(
        source="bugdrop",
        id="BD-1",
        url="u",
        title="battery drain",
        kind="bug_report",
        app="miniride-client",
        platform="iOS",
        version="1.6.0",
        first_version="1.6.0",
        last_version="1.6.0",
        repo="miniride-client",
        gh_repo="o/r",
        component=".",
        language="typescript",
    )
    return Issue(**{**base, **kw})


def rca_state(**issue_kw: Any) -> RunState:
    out = RCAOutput(
        summary="refreshLocally never updates last.at",
        category="own_code",
        root_cause="`refreshLocally()` does not update `this.last.at`, so `nextDelay()` returns 0",
        location=CodeLocation(repo="miniride-client", file="src/eta/poller.ts", function="refreshLocally"),
        claims=[Claim(text="see src/eta/poller.ts", evidence_ids=[])],
        timeline=[],
        reproduction="r",
        fix_direction="update last.at",
    )
    return RunState(
        run_id="r", issue_ref="BD-1", issue=issue(**issue_kw), rca=RCA(actionable=True, output=out)
    )


def test_functions_finds_methods_with_their_class_and_skips_values(sandbox: Sandbox) -> None:
    poller = [n for n, _, _ in fixplan.functions(sandbox.worktree / "src/eta/poller.ts", "typescript")]
    assert poller == ["EtaPoller.start", "EtaPoller.nextDelay", "EtaPoller.refreshLocally"]
    screen = [
        n for n, _, _ in fixplan.functions(sandbox.worktree / "src/screens/RideScreen.tsx", "typescript")
    ]
    assert screen == ["RideScreen"]  # `const prefill = (…)?.x` is a value, not a function


def test_python_and_go_definitions(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("class A:\n    def m(self):\n        pass\n\nasync def f():\n    pass\n")
    (tmp_path / "b.go").write_text("func (s *S) Quote() {}\nfunc helper() {}\n")
    assert [n for n, _, _ in fixplan.functions(tmp_path / "a.py", "python")] == ["A.m", "f"]
    assert [n for n, _, _ in fixplan.functions(tmp_path / "b.go", "go")] == ["Quote", "helper"]


def test_candidates_rank_the_rca_function_and_include_callers(sandbox: Sandbox) -> None:
    cands, changed = fixplan.candidates(sandbox, rca_state())
    ids = [c["id"] for c in cands]
    assert changed == ["src/eta/poller.ts"]
    assert ids[:3] == [
        "src/eta/poller.ts::EtaPoller.start",
        "src/eta/poller.ts::EtaPoller.nextDelay",
        "src/eta/poller.ts::EtaPoller.refreshLocally",
    ]
    by_id = {c["id"]: c["summary"] for c in cands}
    assert "RCA function" in by_id["src/eta/poller.ts::EtaPoller.refreshLocally"]
    assert "named in the RCA" in by_id["src/eta/poller.ts::EtaPoller.nextDelay"]
    assert "references `EtaPoller`" in by_id["src/screens/RideScreen.tsx::RideScreen"]


def test_release_window_lists_the_commit_that_touched_the_file(sandbox: Sandbox) -> None:
    assert fixplan.release_window(sandbox, issue()) == ("v1.5.2", "v1.6.0")
    commits = fixplan.suspect_commits(sandbox, issue(), ["src/eta/poller.ts"])
    assert [c["subject"] for c in commits] == ["refactor(eta): schedule ticks from the last refresh"]
    assert fixplan.release_window(sandbox, issue(first_version="1.5.2")) is None  # no older release


def decision(action: str, chosen: dict[str, Any] | None = None) -> Any:
    return SimpleNamespace(
        action=action, chosen=chosen or {}, p=0.8, band=Band.ACT, ledger_id="l", probabilities={}
    )


class Engine:
    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers

    async def decide(self, decision_id: str, cs: Any, **kw: Any) -> Any:
        return self.answers[decision_id]


async def test_tier_ladder_climbs_from_the_choice_and_drops_unavailable_e2e() -> None:
    deps: Any = SimpleNamespace(engine=Engine({"D14": decision("tier_unit", {"tier": "unit"})}))
    _, ladder, skip, _ = await fixplan.choose_tier(rca_state(), deps, None, {})
    assert ladder == ["unit", "integration", "e2e_env"] and skip is None
    _, ladder, _, _ = await fixplan.choose_tier(rca_state(), deps, "no stack", {})
    assert ladder == ["unit", "integration"]
    deps.engine = Engine({"D14": decision("tier_e2e", {"tier": "e2e_env"})})
    _, ladder, _, _ = await fixplan.choose_tier(rca_state(), deps, None, {})
    assert ladder == ["e2e_env", "unit", "integration"]  # cheaper tiers as the fallback
    rec, ladder, _, _ = await fixplan.choose_tier(rca_state(), deps, "image missing", {})
    assert ladder == ["unit", "integration"] and rec["e2e_unavailable"] == "image missing"
    deps.engine = Engine({"D14": decision("tier_integration", {"tier": "integration"})})
    _, ladder, _, _ = await fixplan.choose_tier(rca_state(), deps, None, {})
    assert ladder == ["integration", "e2e_env", "unit"]
    deps.engine = Engine({"D14": decision("tier_none", {"tier": "cannot_repro"})})
    _, ladder, skip, _ = await fixplan.choose_tier(rca_state(), deps, None, {})
    assert ladder == [] and skip and "cannot be reproduced" in skip


async def test_flag_only_strategy_needs_an_actual_rollback() -> None:
    deps: Any = SimpleNamespace(engine=Engine({"D13": decision("skip_fix", {"strategy": "flag_only"})}))
    st = rca_state()
    rec, skip, _ = await fixplan.choose_strategy(st, deps, [], [])
    assert skip is None and "not rolled back" in rec["note"]
    st.mitigation = Mitigation(flag="notif_router_v2", action="rolled_back")
    _, skip, _ = await fixplan.choose_strategy(st, deps, [], [])
    assert skip and "notif_router_v2 rolled back" in skip
    deps.engine = Engine({"D13": decision("escalate_to_owner", {"strategy": "needs_human"})})
    _, skip, _ = await fixplan.choose_strategy(st, deps, [], [])
    assert skip == "needs a human decision (D13)"


async def test_a_skipped_plan_escalates_at_the_ship_gate() -> None:
    st = rca_state()
    st.fix_plan = FixPlan(skip="needs a human decision (D13)")
    out = await nodes.ship_gate(st, SimpleNamespace())  # pyright: ignore[reportArgumentType]
    assert out["ship"].outcome == "escalate"
    st.fix_plan = FixPlan(skip="cannot be reproduced automatically (D14)")
    out = await nodes.ship_gate(st, SimpleNamespace())  # pyright: ignore[reportArgumentType]
    assert out["ship"].outcome == "rca_only"


def test_e2e_specs_are_test_files_and_run_by_tier() -> None:
    i = issue()
    spec = "e2e/booking-weak.spec.ts"
    assert nodes._repro_cmd(i, spec) == f"pnpm exec playwright test {spec}"  # pyright: ignore[reportPrivateUsage]
    assert nodes._repro_cmd(i, "test/poller.test.ts") == "pnpm exec vitest run test/poller.test.ts"  # pyright: ignore[reportPrivateUsage]
    assert nodes._tier_problem("e2e_env", i, "test/poller.test.ts")  # pyright: ignore[reportPrivateUsage]
    assert nodes._tier_problem("unit", i, "e2e/x.spec.ts")  # pyright: ignore[reportPrivateUsage]
    assert nodes._tier_problem("integration", i, "test/x.test.ts") is None  # pyright: ignore[reportPrivateUsage]
    assert e2e.is_e2e_cmd(e2e.e2e_cmd("e2e/x.spec.ts", "."))


def test_captured_env_maps_the_reported_network_profile() -> None:
    report = {
        "network": {"effectiveType": "2g", "rtt": 2000, "downlink": 0.25},
        "city": "sf",
        "flags": {"notif_router_v2": False},
    }
    env = e2e.captured_env(report, {}, [])
    assert env["network"]["latencyMs"] == 2000 and env["network"]["downloadKbps"] == 250
    assert env["city"] == "sf" and env["flags"] == {"notif_router_v2": False}
    assert e2e.captured_env({}, {}, []) == {}


def test_captured_env_takes_flag_exposure_from_the_crash_event() -> None:
    event = {"flags": {"notif_router_v2": True}, "device": {"os": "Android 14"}, "culprit": "/"}
    env = e2e.captured_env({}, event, [])
    assert env == {"flags": {"notif_router_v2": True}, "device": {"os": "Android 14"}, "route": "/"}


def test_playwright_attachment_noise_is_dropped() -> None:
    raw = (
        "  1) e2e/x.spec.ts:3 › books once\n    Error: expect(received).toBe(expected)\n"
        "    attachment #1: video (video/webm) ──────\n    .da-e2e/test-results/x/video.webm\n"
        "    ────────────────────────\n    Usage:\n        npx playwright show-trace .da-e2e/test-results/x/t.zip\n"
        "  1 failed\n"
    )
    out = e2e.clean_output(raw)
    assert "expect(received).toBe(expected)" in out and "1 failed" in out
    assert "video.webm" not in out and "show-trace" not in out and "──" not in out


async def test_until_records_the_node_it_stopped_after(tmp_path: Path) -> None:
    from debugassist.pipeline.graph import wrap

    async def step(state: RunState, deps: Any) -> dict[str, Any]:
        return {"costs": {"x": 0.0}}

    deps: Any = SimpleNamespace(extra={"until": "mitigate"}, run_dir=tmp_path)
    out = await wrap("mitigate", step, deps, lambda _m: None)(rca_state())
    assert out["status"] == "stopped" and out["stopped_after"] == "mitigate"
    deps.extra = {}
    out = await wrap("mitigate", step, deps, lambda _m: None)(rca_state())
    assert "status" not in out


async def test_d12_two_stage_through_the_real_engine_with_many_candidates(sandbox: Sandbox) -> None:
    """More than `max_direct` candidates → one Clef question per candidate; ids must be Clef-safe."""
    from debugassist.decisions.backends.mock import MockDecider
    from debugassist.decisions.engine import DecisionEngine

    many = "\n".join(f"export function helper{i}() {{\n  return {i};\n}}" for i in range(45))
    (sandbox.worktree / "src" / "eta" / "poller.ts").write_text(POLLER_V2 + many + "\n")
    deps: Any = SimpleNamespace(engine=DecisionEngine(MockDecider(), ledger=None))
    rec, focus, n, _ = await fixplan.localize(sandbox, rca_state(), deps)
    assert n > 40
    ids = [c["id"] for c in fixplan.candidates(sandbox, rca_state())[0]]
    assert rec["choice"] in [*ids, "none"] and all(f in ids for f in focus)


@pytest.mark.parametrize(
    ("rollout", "significant", "action", "detail"),
    [
        (0, True, "none", "already at 0%"),
        (5, True, "dry_run", "5% → 0% (dry run"),
        (5, False, "none", "no rollback"),
    ],
)
async def test_mitigation_rolls_back_only_a_live_significant_flag(
    monkeypatch: pytest.MonkeyPatch, rollout: int, significant: bool, action: str, detail: str
) -> None:
    from debugassist.core.policy import Verdict
    from debugassist.mcp_servers import feature_flags as ff

    corr: dict[str, Any] = {
        "exposed": {}, "unexposed": {}, "z": 10.0, "p_value": 1e-9,
        "significant": significant, "share_of_affected_exposed": 1.0,
    }  # fmt: skip
    monkeypatch.setattr(ff, "flag_crash_correlation", lambda fp, flag: corr)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    monkeypatch.setattr(ff, "get_flag", lambda flag: {"rollout_pct": rollout})  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    monkeypatch.setattr(
        ff,
        "rollback_flag",
        lambda flag, pct, reason, dry_run: {"applied": not dry_run, "from_percent": rollout},  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    )
    st = rca_state(fingerprint="fp1")
    assert st.rca and st.rca.output
    st.rca.output.implicated_flag = "notif_router_v2"
    deps: Any = SimpleNamespace(
        engine=Engine({"D11": decision("rollback_flag")}),
        gate=SimpleNamespace(verdict=lambda _a: Verdict.DRY_RUN),  # pyright: ignore[reportUnknownLambdaType]
    )
    m = (await nodes.mitigate(st, deps))["mitigation"]
    assert m.action == action and detail in m.detail


async def test_llm_nodes_do_not_start_once_the_run_budget_is_spent(tmp_path: Path) -> None:
    from debugassist.pipeline import budget
    from debugassist.pipeline.graph import wrap

    calls: list[str] = []

    async def step(state: RunState, deps: Any) -> dict[str, Any]:
        calls.append("ran")
        return {"costs": {**state.costs, "fix": 0.1}}

    class Ledger:
        async def list(self, *, run_id: str | None = None, decision_id: str | None = None) -> list[Any]:
            return [SimpleNamespace(cost_usd=0.25)]

    deps: Any = SimpleNamespace(
        extra={},
        run_dir=tmp_path,
        agent_type={"name": "t", "run_budget_usd": 1.0},
        engine=SimpleNamespace(ledger=Ledger()),
    )
    st = rca_state()
    st.costs = {"classify_rca": 0.5}
    out = await wrap("fix", step, deps, lambda _m: None)(st)
    assert calls == ["ran"] and deps.extra["budget_remaining"] == pytest.approx(0.25)
    assert budget.cap({"max_budget_usd": 1.0}, deps)["max_budget_usd"] == pytest.approx(0.25)
    st.costs = {"classify_rca": 0.8}
    out = await wrap("fix", step, deps, lambda _m: None)(st)
    assert calls == ["ran"] and out["status"] == "failed" and "run budget exhausted" in out["errors"][-2]
    out = await wrap("validate", step, deps, lambda _m: None)(st)  # deterministic nodes still run
    assert calls == ["ran", "ran"]
