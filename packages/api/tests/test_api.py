from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from debugassist.api import app as app_module
from debugassist.api.data import Paths

RUN = "20261005-095731-vit-1001"


def state(status: str = "watching") -> dict[str, object]:
    return {
        "run_id": RUN,
        "issue_ref": "VIT-1001",
        "status": status,
        "llm_mode": "mock",
        "issue": {
            "id": "VIT-1001",
            "source": "vitals",
            "title": "TypeError",
            "app": "miniride-client",
            "last_version": "1.6.1",
        },
        "triage": {
            "priority": "P1",
            "severity": "S2",
            "owner_team": "rider-app",
            "oncall": "aiko",
            "jira_key": "MOCK-1",
        },
        "rca": {
            "output": {"category": "own_code", "location": {"file": "src/router.ts", "function": "routeV2"}}
        },
        "validation": {"passed": True},
        "fix_attempts": [{"tier": "unit"}],
        "ship": {"outcome": "open_pr"},
        "pr": {"url": "mock://pr/1"},
        "costs": {"classify_rca": 0.01, "fix": 0.02},
        "timings_ms": {"ingest": 100, "classify_rca": 2000, "fix": 3000},
        "errors": [],
    }


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    run = tmp_path / "data" / "runs" / RUN
    (run / "nodes").mkdir(parents=True)
    (run / "agents").mkdir()
    (run / "state.json").write_text(json.dumps(state()))
    for i, n in enumerate(["ingest", "auto_triage", "context_collector", "classify_rca", "fix"]):
        (run / "nodes" / f"{i:02d}-{n}.json").write_text("{}")
    (run / "agents" / "fix.jsonl").write_text(
        json.dumps({"at": "2026-10-05T10:00:02", "kind": "tool", "tool": "read_file"}) + "\n"
    )
    (run / "agents" / "classify_rca.jsonl").write_text(
        json.dumps({"at": "2026-10-05T10:00:01", "kind": "model"}) + "\n" + '{"partial'
    )
    con = sqlite3.connect(tmp_path / "data" / "debugassist.db")
    con.execute(
        "CREATE TABLE decision_ledger (id TEXT, created_at TEXT, run_id TEXT, issue_id TEXT, parent_id TEXT,"
        " decision_id TEXT, backend TEXT, model TEXT, mode TEXT, questions TEXT, answers TEXT, chosen TEXT,"
        " confidence REAL, band TEXT, action TEXT, latency_ms INTEGER, input_tokens INTEGER,"
        " output_tokens INTEGER, cost_usd REAL, n_calls INTEGER, fallback_reason TEXT, outcome_label TEXT)"
    )
    rows = [
        ("a", "2026-10-05T10:00:00", RUN, "D01_triage", 0.9, '{"correct": true}'),
        ("b", "2026-10-05T10:00:01", RUN, "D01_triage", 0.6, '{"correct": false}'),
        ("c", "2026-10-05T10:00:02", "other", "D16_ship_gate", 0.7, None),
    ]
    for rid, at, run_id, did, conf, label in rows:
        con.execute(
            "INSERT INTO decision_ledger VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rid, at, run_id, "VIT-1001", None, did, "workers_ai", "clef", "live", "{}", "{}", "{}", conf,
             "act", "x", 200, 10, 5, 0.0001, 1, None, label),
        )  # fmt: skip
    con.commit()
    con.close()
    monkeypatch.setattr(app_module, "PATHS", Paths(data=tmp_path / "data", root=Path(__file__).parents[3]))

    def no_sources(url: str, **params: object) -> list[object]:
        return []

    monkeypatch.setattr(app_module, "_get", no_sources)
    return TestClient(app_module.app)


def test_runs_and_run_detail(client: TestClient) -> None:
    rows = client.get("/api/runs").json()
    assert [r["run_id"] for r in rows] == [RUN]
    r = rows[0]
    assert r["priority"] == "P1" and r["location"] == "src/router.ts → routeV2" and r["cost_usd"] == 0.03
    detail = client.get(f"/api/runs/{RUN}").json()
    graph = {n["id"]: n["status"] for n in detail["graph"]}
    assert graph["fix"] == "done" and graph["mitigate"] == "skipped" and graph["validate"] == "skipped"
    assert client.get("/api/runs/nope").status_code == 404
    assert client.get("/api/runs/..%2F..").status_code == 404


def test_calls_merge_agent_logs_in_time_order_and_skip_partial_lines(client: TestClient) -> None:
    calls = client.get(f"/api/runs/{RUN}/calls").json()
    assert [c["kind"] for c in calls] == ["model", "tool"]


def test_decisions_carry_template_policy(client: TestClient) -> None:
    ds = client.get(f"/api/runs/{RUN}/decisions").json()
    assert [d["id"] for d in ds] == ["a", "b"]
    assert set(ds[0]["policy"]) == {"question", "tau_high", "tau_low"} and ds[0]["description"]


def test_metrics_compute_brier_from_labelled_decisions(client: TestClient) -> None:
    m = client.get("/api/metrics").json()
    d1 = next(d for d in m["decisions"] if d["decision_id"] == "D01_triage")
    assert d1["n"] == 2 and d1["labelled"] == 2 and d1["accuracy"] == 0.5
    assert d1["brier"] == round(((0.9 - 1) ** 2 + (0.6 - 0) ** 2) / 2, 4)
    assert m["impact"]["by_llm_mode"]["mock"]["prs"] == 1


def test_feedback_round_trip(client: TestClient) -> None:
    r = client.post(
        f"/api/runs/{RUN}/feedback", json={"target": "claim:2", "reaction": "down", "comment": "wrong file"}
    )
    assert r.status_code == 201
    assert client.get(f"/api/runs/{RUN}/feedback").json()[0]["comment"] == "wrong file"
    assert client.post(f"/api/runs/{RUN}/feedback", json={"reaction": "meh"}).status_code == 422


def test_marketplace_lists_the_pr_authoring_skill(client: TestClient) -> None:
    m = client.get("/api/marketplace").json()
    skill = next(s for s in m["skills"] if s["name"] == "pr-authoring")
    assert skill["tokens"] > 100 and "pipeline (pr_and_notify)" in skill["used_by"]
    assert any(t["id"].startswith("D17") for t in m["templates"]) and "web-crash" in m["agent_types"]


def test_stream_ends_when_the_run_is_not_running(client: TestClient) -> None:
    with client.stream("GET", f"/api/runs/{RUN}/stream") as r:
        body = "".join(r.iter_text())
    assert "event: call" in body and "event: graph" in body and body.rstrip().endswith("data: {}")


def test_artifact_paths_cannot_escape(client: TestClient) -> None:
    assert client.get(f"/api/runs/{RUN}/artifacts").json() == []
    assert client.get(f"/api/runs/{RUN}/artifacts/../../state.json").status_code == 404
