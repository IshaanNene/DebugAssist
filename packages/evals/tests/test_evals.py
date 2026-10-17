from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from debugassist.core import ablation
from debugassist.evals import labels, metrics, report, score
from debugassist.scenarios.catalog import get_bug


def out(file: str, function: str, category: str = "own_code") -> dict[str, Any]:
    return {"location": {"file": file, "function": function}, "category": category}


def test_rca_verdict_exact_directional_wrong() -> None:
    b1, b4 = get_bug("BUG-001"), get_bug("BUG-004")  # client tick(); dispatch eta_seconds()
    assert score.rca_verdict(out("src/eta/poller.ts", "EtaPoller.tick"), b1) == "exact"
    assert score.rca_verdict(out("src/eta/poller.ts", "refreshLocally"), b1) == "directional"
    assert score.rca_verdict(out("src/api/rides.ts", "requestRide"), b1) == "wrong"
    assert (
        score.rca_verdict(out("src/dispatch/matching.py", "eta_seconds"), b4) == "exact"
    )  # relative to component
    assert score.rca_verdict(None, b1) == "none"


def test_outcome_and_changed_lines_and_similarity() -> None:
    assert score.outcome_ok("draft_pr", get_bug("BUG-001")) and not score.outcome_ok(
        "rca_only", get_bug("BUG-001")
    )
    assert score.outcome_ok("rca_only", get_bug("BUG-006"))
    diff = "diff --git a/src/a.ts b/src/a.ts\n--- a/src/a.ts\n+++ b/src/a.ts\n-  x = 1\n+  x = 2\ndiff --git a/test/a.test.ts b/test/a.test.ts\n+expect(1)\n"
    assert score.changed_lines(diff) == ["-x = 1", "+x = 2"]
    assert score.diff_similarity(diff, diff) == 1.0 and score.diff_similarity("", diff) is None


def test_catalog_labels_judge_the_decisions_it_knows() -> None:
    b2 = get_bug("BUG-002")  # P1, own_code, flag rollback, unit tier, PR
    assert labels.judge("D01_triage", {"priority": 3.1}, None, b2) == {
        "correct": True,
        "expected": "P1",
        "got": "P1",
    }
    assert labels.judge("D05_categorize", {"category": "network"}, None, b2)["correct"] is False  # type: ignore[index]
    assert labels.judge("D11_mitigation", {}, "rollback_flag", b2)["correct"] is True  # type: ignore[index]
    assert labels.judge("D14_validation_tier", {}, "tier_e2e", b2)["got"] == "e2e_env"  # type: ignore[index]
    assert labels.judge("D16_ship_gate", {}, "open_pr", b2)["correct"] is True  # type: ignore[index]
    names = {"names": {"c4": "src/notifications/router.ts::routeV2"}}
    d12 = labels.judge("D12_localization", {"location": "c4"}, "focus_location", b2, names)
    assert d12 is not None and d12["correct"] is True
    d11 = labels.judge("D11_mitigation", {}, "rollback_flag", get_bug("BUG-001"))  # BUG-001 has no flag
    assert d11 is not None and d11["correct"] is False
    assert labels.judge("D09_grounding", {}, "keep", b2) is None


def test_d12_names_come_back_from_the_rendered_question() -> None:
    q = {
        "location": {
            "type": "choice",
            "criteria": {
                "c1": "src/eta/poller.ts::EtaPoller.tick: private async tick() { (line 75) — RCA function",
                "none": "none of these",
            },
        }
    }
    assert labels.d12_names(q) == {"c1": "src/eta/poller.ts::EtaPoller.tick"}


def test_metrics_brier_ece_and_selective_accuracy() -> None:
    pts = [
        metrics.Point("D05", "clef", "clef", c, ok, 100.0, 0.0002)
        for c, ok in [(0.9, True), (0.8, True), (0.7, False), (0.2, False)]
    ]
    s = metrics.summarize(pts, tau=0.75)
    assert s["accuracy"] == 0.5 and s["coverage_at_tau"] == 0.5 and s["accuracy_at_tau"] == 1.0
    assert s["brier"] == round((0.01 + 0.04 + 0.49 + 0.04) / 4, 4)
    assert 0 <= (s["ece"] or 0) <= 1 and s["usd_per_1k"] == 0.2


def test_ablation_switches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DA_ABLATE", "D3, d09")
    assert ablation.ablated("D03") and ablation.ablated("D9") and not ablation.ablated("D12")
    monkeypatch.setenv("DA_DECIDER", "clef-flash")
    assert ablation.label() == "clef-flash-no-d03-d09"
    monkeypatch.setenv("DA_DECIDER", "gpt")
    with pytest.raises(ValueError):
        ablation.decider()


def test_report_aggregates_seeds_and_writes_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = tmp_path / "runs" / "20261005-000000"
    run.mkdir(parents=True)
    rows = [
        {"config": "routed", "seed": s, "bug": b, "rca": rca, "category_ok": True, "outcome_ok": True, "validated": v, "hidden_tests": v,
         "diff_similarity": 0.5, "claims_unsupported": 0, "turns": 10, "usd": 0.2, "discovery_to_rca_s": 60.0, "pipeline_s": 100.0, "rca_location": "x", "run_id": f"r{s}{b}"}
        for s in (1, 2) for b, rca, v in (("BUG-001", "exact", True), ("BUG-002", "directional" if s == 1 else "exact", False))
    ]  # fmt: skip
    (run / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    monkeypatch.setattr(report, "REPORTS", tmp_path / "reports")
    cfg = report.by_config(report.load_results([run]))[0]
    assert cfg["runs"] == 4 and cfg["seeds"] == 2 and cfg["rca_exact"] == "0.75 ± 0.25"
    pts = [metrics.Point("D05_categorize", "clef", "clef", 0.9, True, 100, 0.0)]
    out_dir = report.write([run], [], pts, {"D05_categorize": 0.6})
    md = (out_dir / "report.md").read_text()
    assert (
        "| routed | 4 | 2 | 2 |" in md
        and (out_dir / "results.csv").is_file()
        and (out_dir / "rca_by_config.svg").is_file()
    )


def test_points_skip_unlabelled_rows() -> None:
    rows = [
        SimpleNamespace(
            outcome_label={"correct": True},
            outcome_source="catalog",
            decision_id="D05",
            backend="clef",
            model="clef",
            confidence=0.9,
            latency_ms=1,
            cost_usd=0.0,
        ),
        SimpleNamespace(
            outcome_label=None,
            outcome_source=None,
            decision_id="D05",
            backend="clef",
            model="clef",
            confidence=0.9,
            latency_ms=1,
            cost_usd=0.0,
        ),
        SimpleNamespace(
            outcome_label='{"correct": false}',
            outcome_source="review",
            decision_id="D09",
            backend="clef",
            model="clef",
            confidence=0.4,
            latency_ms=1,
            cost_usd=0.0,
        ),
    ]
    assert len(metrics.points(rows)) == 2 and len(metrics.points(rows, source="catalog")) == 1


def test_client_path_is_not_credited_to_a_services_module() -> None:
    from debugassist.evals.score import rca_verdict
    from debugassist.scenarios.catalog import get_bug

    bug = get_bug("BUG-019")  # payments/internal/fares/fares.go → Rates
    wrong_repo = {"location": {"file": "src/screens/RequestRide.tsx", "function": "formatMoney"}}
    relative = {"location": {"file": "internal/fares/fares.go", "function": "Rates"}}
    assert rca_verdict(wrong_repo, bug) == "wrong"
    gateway = get_bug("BUG-014")  # gateway/src/backends.ts: a client src/ path named as the client repo
    client = {"location": {"repo": "miniride-client", "file": "src/screens/Search.tsx", "function": "Search"}}
    assert rca_verdict(client, gateway) == "wrong"
    assert rca_verdict(relative, bug) == "exact"


def test_context_anatomy_splits_input_into_prefix_tools_and_model(tmp_path: Path) -> None:
    import json as _json

    from debugassist.evals import context as ctx

    log = tmp_path / "fix.jsonl"
    ev = [
        {"kind": "model", "turn": 1, "input_tokens": 1000, "output_tokens": 50, "cached_tokens": 0},
        {"kind": "tool", "turn": 1, "tool": "read_file"},
        {"kind": "model", "turn": 2, "input_tokens": 1550, "output_tokens": 20, "cached_tokens": 1000},
        {"kind": "model", "turn": 3, "input_tokens": 1570, "output_tokens": 10, "cached_tokens": 1550},
        {"kind": "done", "turn": 3},
        {
            "kind": "model",
            "turn": 1,
            "input_tokens": 900,
            "output_tokens": 10,
            "cached_tokens": 0,
        },  # 2nd agent run
    ]
    log.write_text("\n".join(_json.dumps(e) for e in ev))
    a = ctx.anatomy("none", log)
    assert a is not None and a.turns == 4
    assert a.input_tokens == 1000 + 1550 + 1570 + 900
    assert a.prefix_total == 1000 * 3 + 900  # each agent run has its own prefix
    assert a.tools_added == {"read_file": 500}  # turn 1 added 550: 50 own output + 500 tool result
    assert a.tools_total == {"read_file": 1000}  # re-sent on turns 2 and 3
    assert a.prefix_total + a.model_total + sum(a.tools_total.values()) == a.input_tokens


def test_wilson_intervals_match_known_values() -> None:
    """Roadmap 081: e.g. 49/75 → 0.541–0.751; k = 0 and k = n stay inside [0, 1]."""
    from debugassist.evals.stats import rate_with_interval, wilson

    lo, hi = wilson(49, 75)
    assert round(lo, 3) == 0.541 and round(hi, 3) == 0.751
    assert wilson(0, 10)[0] == 0.0 and wilson(10, 10)[1] == 1.0
    assert wilson(0, 0) == (0.0, 1.0)
    assert rate_with_interval(49, 75) == "0.65 [0.54–0.75] (49/75)"


def test_charts_render_byte_identical(tmp_path: Path) -> None:
    """Roadmap 070: the same data renders the same SVG bytes (no date, no random ids)."""
    from debugassist.evals import report

    rows = [{"config": "routed", "rca": "exact"}, {"config": "routed", "rca": "directional"}]
    report._chart_configs(rows, tmp_path / "a.svg")  # pyright: ignore[reportPrivateUsage]
    report._chart_configs(rows, tmp_path / "b.svg")  # pyright: ignore[reportPrivateUsage]
    assert (tmp_path / "a.svg").read_bytes() == (tmp_path / "b.svg").read_bytes()
    assert b"<dc:date>" not in (tmp_path / "a.svg").read_bytes()


def test_mcnemar_and_paired_comparisons() -> None:
    """ROADMAP-100 082: a difference between paired arms is claimed only when the exact test supports it."""
    from debugassist.evals import report
    from debugassist.evals.stats import mcnemar

    assert mcnemar(0, 0) == 1.0
    assert round(mcnemar(1, 4), 3) == 0.375  # 2 * P(X <= 1), X ~ Bin(5, 1/2)
    assert mcnemar(10, 0) < 0.01

    def run(config: str, bug: str, exact: bool) -> dict[str, object]:
        return {
            "config": config,
            "bug": bug,
            "seed": 1,
            "rca": "exact" if exact else "wrong",
            "validated": exact,
        }

    close = [run("a", f"B{i}", i < 6) for i in range(10)] + [run("b", f"B{i}", i < 5) for i in range(10)]
    [row, _] = report.paired_comparisons(close)
    assert (row["only_a"], row["only_b"], row["verdict"]) == (1, 0, "no evidence of a difference")
    far = [run("a", f"B{i}", True) for i in range(12)] + [run("b", f"B{i}", False) for i in range(12)]
    assert report.paired_comparisons(far)[0]["verdict"] == "a better"


def test_latency_profile_per_node(tmp_path: Path) -> None:
    """ROADMAP-100 041."""
    from debugassist.evals.latency import percentile, profile

    files: list[Path] = []
    for i, fix_ms in enumerate([10_000, 20_000, 30_000, 40_000, 400_000]):
        d = tmp_path / f"2026101{i}-run"
        d.mkdir()
        (d / "state.json").write_text(json.dumps({"timings_ms": {"ingest": 100, "fix": fix_ms}}))
        files.append(d / "state.json")
    (tmp_path / "broken.json").write_text("{")
    rows = {r["node"]: r for r in profile([*files, tmp_path / "broken.json"])}
    assert list(rows) == ["ingest", "fix", "run"]
    assert (rows["fix"]["runs"], rows["fix"]["p50_s"], rows["fix"]["max_s"]) == (5, 30.0, 400.0)
    assert rows["fix"]["p95_s"] == 400.0 and rows["run"]["p50_s"] == 30.1
    assert percentile([1, 2, 3, 4], 50) == 2
