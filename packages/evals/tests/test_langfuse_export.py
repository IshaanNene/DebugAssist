from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from debugassist.evals import langfuse_export as lx

ROW = {
    "run_id": "20261010-093546-vit-1001",
    "bug": "BUG-004",
    "issue": "VIT-1001",
    "agent_type": "backend-error",
    "config": "context-lean",
    "arm": "context-lean",
    "commit": "1ae93f2",
    "model": "openai/gpt-6-luna",
    "rca": "exact",
    "rca_location": "dispatch/src/dispatch/matching.py → eta_seconds",
    "category_ok": True,
    "validated": True,
    "hidden_tests": True,
    "usd": 0.0129,
    "turns": 22,
    "wall_s": 200.5,
}


def _sweep(tmp_path: Path, rows: list[dict[str, Any]]) -> Path:
    d = tmp_path / "20261010-093503"
    d.mkdir()
    (d / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return d


def test_one_experiment_item_per_scored_run(tmp_path: Path) -> None:
    excluded = {**ROW, "run_id": "20261010-092947-vit-1001", "excluded": "first lean version"}
    unscored = {**ROW, "run_id": "20261010-100000-vit-1002", "rca": ""}
    d = _sweep(tmp_path, [ROW, excluded, unscored])
    mem, posted = InMemorySpanExporter(), list[tuple[str, dict[str, Any]]]()
    expected = {"category": "own_code", "expected_outcome": "pr", "location": "miniride-services/x.py → f"}
    out = lx.export(
        [d], exporter=mem, post=lambda p, b: posted.append((p, b)), expected=lambda _bug: expected
    )

    assert out["items"] == 1 and out["experiments"] == ["context-lean · 20261010-093503"]
    (span,) = mem.get_finished_spans()
    assert span.context is not None
    a = span.attributes or {}
    assert a["langfuse.experiment.id"] == "20261010-093503-context-lean"
    assert a["langfuse.experiment.item.id"] == "BUG-004"
    assert a["langfuse.experiment.dataset.id"] == lx.DATASET
    # the item root points at itself, as Langfuse requires
    assert a["langfuse.experiment.item.root_observation_id"] == format(span.context.span_id, "016x")
    assert json.loads(str(a["langfuse.experiment.item.expected_output"])) == expected
    assert json.loads(str(a["langfuse.observation.output"]))["validated"] is True
    assert span.end_time is not None and span.start_time is not None
    assert round((span.end_time - span.start_time) / 1e9, 1) == 200.5

    scores = {b["name"]: b for p, b in posted if p == "/api/public/scores"}
    assert set(scores) == {"rca", "category_ok", "validated", "hidden_tests", "usd", "turns"}
    assert scores["rca"]["value"] == 1.0 and scores["hidden_tests"]["dataType"] == "BOOLEAN"
    assert all(b["traceId"] == format(span.context.trace_id, "032x") for b in scores.values())
    assert all(b["observationId"] == format(span.context.span_id, "016x") for b in scores.values())


def test_ids_are_stable_so_a_reexport_updates_in_place(tmp_path: Path) -> None:
    d = _sweep(tmp_path, [ROW])
    first, second = InMemorySpanExporter(), InMemorySpanExporter()
    posts: list[dict[str, Any]] = []
    lx.export([d], exporter=first, post=lambda _p, b: posts.append(b), expected=lambda _b: None)
    lx.export([d], exporter=second, post=lambda _p, b: posts.append(b), expected=lambda _b: None)
    a, b = first.get_finished_spans()[0], second.get_finished_spans()[0]
    assert a.context is not None and b.context is not None
    assert (a.context.trace_id, a.context.span_id) == (b.context.trace_id, b.context.span_id)
    assert len({p["id"] for p in posts}) == len(posts) // 2  # same score ids both times


def test_directional_scores_half_and_missing_hidden_is_skipped() -> None:
    it = lx.item({**ROW, "rca": "directional", "hidden_tests": None}, None)
    names = {n: v for n, v, _ in it["scores"]}
    assert names["rca"] == 0.5 and "hidden_tests" not in names
    assert (
        lx.experiment_of({**ROW, "config": "routed", "arm": "fix-quality"}, "s")[1]
        == "routed · fix-quality · s"
    )
