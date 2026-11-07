from __future__ import annotations

import json
from pathlib import Path

from debugassist.evals import timings


def node(run: Path, i: int, name: str, ms: int, kind: str | None = None) -> None:
    (run / "nodes").mkdir(parents=True, exist_ok=True)
    rec: dict[str, object] = {"node": name, "kind": kind, "ms": ms, "update": {}}
    (run / "nodes" / f"{i:02d}-{name}.json").write_text(json.dumps(rec))


def test_steps_run_back_to_back_and_a_repeated_step_is_listed_twice(tmp_path: Path) -> None:
    run = tmp_path / "20261007-000000-vit-1"
    node(run, 0, "ingest", 20, "deterministic")
    node(run, 1, "fix", 1000, "llm")
    node(run, 2, "validate", 300, "deterministic")
    node(run, 3, "fix", 500, "llm")
    t = timings.run_timings(run)
    assert t is not None
    assert [(s.node, s.start_ms, s.ms) for s in t.steps] == [
        ("ingest", 0, 20),
        ("fix", 20, 1000),
        ("validate", 1020, 300),
        ("fix", 1320, 500),
    ]
    assert t.steps_ms == 1820


def test_kind_falls_back_to_the_plan_and_numbering_past_99_keeps_order(tmp_path: Path) -> None:
    run = tmp_path / "r"
    for i in range(101):
        node(run, i, "classify_rca" if i == 100 else "fix", 1, None if i == 100 else "llm")
    t = timings.run_timings(run)
    assert t is not None and t.steps[-1].node == "classify_rca" and t.steps[-1].kind == "llm+clef"


def test_export_lists_runs_without_node_files_as_missing(tmp_path: Path) -> None:
    node(tmp_path / "a", 0, "ingest", 5, "deterministic")
    (tmp_path / "half" / "nodes").mkdir(parents=True)
    (tmp_path / "half" / "nodes" / "00-ingest.json").write_text("{not json")
    out = timings.export(["a", "b", "a", "half"], tmp_path)
    assert [r["run_id"] for r in out["runs"]] == ["a"]
    assert out["missing"] == ["b", "half"]
