"""The P4 servers against recorded live responses (fixtures/live, see record_live.py) — no stack needed."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from debugassist.mcp_servers import bug_reports, incidents, logging_, metrics_profiles, releases, tracing

LIVE = Path(__file__).parent / "fixtures" / "live"


def fixture(name: str) -> str:
    return (LIVE / name).read_text()


def client(base: str, routes: dict[str, str | Callable[[httpx.Request], httpx.Response]]) -> httpx.Client:
    """An httpx client that answers each path from a fixture (or a handler); anything else is a 404."""

    def handle(request: httpx.Request) -> httpx.Response:
        route = routes.get(request.url.path)
        if route is None:
            return httpx.Response(404, json={"error": "no fixture"})
        if callable(route):
            return route(request)
        return httpx.Response(200, text=route, headers={"content-type": "application/json"})

    return httpx.Client(base_url=base, transport=httpx.MockTransport(handle))


def test_bug_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        bug_reports,
        "_http",
        client(
            "http://bugdrop",
            {
                "/api/reports": fixture("bugdrop_reports.json"),
                "/api/reports/BD-1001": fixture("bugdrop_report.json"),
                "/api/reports/BD-1001/logs": fixture("bugdrop_logs_network.json"),
                "/api/reports/BD-1001/screenshots": fixture("bugdrop_screenshots.json"),
                "/api/reports/BD-1001/ui-state-timeline": fixture("bugdrop_timeline.json"),
            },
        ),
    )
    reports = bug_reports.list_reports()
    assert reports["evidence_id"].startswith("ev_bugdrop_") and reports["items"][0]["id"] == "BD-1001"
    report = bug_reports.get_report("BD-1001")
    assert "notification" in report["description"] and report["files"][0]["kind"] == "app_screenshot"
    logs = bug_reports.get_logs("BD-1001", "network", limit=2)
    assert logs["log_kind"] == "network" and logs["returned"] == 2 and logs["next_offset"] == 2
    assert "error" in bug_reports.get_logs("BD-1001", "everything")
    assert bug_reports.get_screenshots("BD-1001")["evidence_id"].startswith("ev_screenshot_")
    assert "total_hidden_s" in bug_reports.get_ui_state_timeline("BD-1001")


def test_incidents(monkeypatch: pytest.MonkeyPatch) -> None:
    deps = json.loads(fixture("incidents_dependencies.json"))
    deps["push-provider"]["status"] = "degraded"  # one constructed outage on top of the live response
    active = [
        {
            "id": "INC-7",
            "title": "Push delays",
            "severity": "sev2",
            "status": "active",
            "services": ["gateway"],
        },
        {"id": "INC-6", "title": "Old", "severity": "sev3", "status": "resolved", "services": ["dispatch"]},
    ]
    monkeypatch.setattr(
        incidents,
        "_http",
        client(
            "http://incidents", {"/api/dependencies": json.dumps(deps), "/api/incidents": json.dumps(active)}
        ),
    )
    listed = incidents.list_active_incidents()
    assert [i["id"] for i in listed["items"]] == ["INC-7"]
    assert incidents.list_active_incidents(service="payments")["items"] == []
    status = incidents.dependency_status()
    assert status["not_operational"] == ["push-provider"]


def test_tracing(monkeypatch: pytest.MonkeyPatch) -> None:
    trace_doc = fixture("jaeger_trace.ndjson")
    trace_id = json.loads(trace_doc.splitlines()[0])["result"]["resourceSpans"][0]["scopeSpans"][0]["spans"][
        0
    ]["traceId"]
    monkeypatch.setattr(
        tracing,
        "_http",
        client(
            "http://jaeger",
            {
                "/api/v3/operations": fixture("jaeger_operations_dispatch.json"),
                "/api/v3/traces": fixture("jaeger_traces_dispatch_places.ndjson"),
                f"/api/v3/traces/{trace_id}": trace_doc,
                "/api/dependencies": fixture("jaeger_dependencies.json"),
            },
        ),
    )
    found = tracing.find_traces("dispatch", lookback_minutes=1440, limit=5)
    assert found["total"] >= 1 and all("/healthz" not in t["root"] for t in found["items"])
    one = tracing.get_trace(trace_id)
    assert one["critical_path"] and one["spans"] >= 1 and one["duration_ms"] > 0
    deps = tracing.service_dependencies()
    assert (
        all(e["parent"] != e["child"] for e in deps["edges"])
        and deps["edges"][0]["calls"] >= deps["edges"][-1]["calls"]
    )


def test_logging_prunes(monkeypatch: pytest.MonkeyPatch) -> None:
    def query(request: httpx.Request) -> httpx.Response:
        body = (
            fixture("loki_stats_gateway.json")
            if "count_over_time" in request.url.params["query"]
            else fixture("loki_query_range_gateway.json")
        )
        return httpx.Response(200, text=body)

    monkeypatch.setattr(
        logging_,
        "_http",
        client("http://loki", {"/loki/api/v1/query_range": query, "/loki/api/v1/query": query}),
    )
    out = logging_.query_logs(service="gateway", minutes=1440, limit=10)
    assert out["lines_scanned"] == 40 and out["total"] < out["lines_scanned"]  # repeats collapsed
    assert sum(g["count"] for g in out["items"]) <= out["lines_scanned"]
    stats = logging_.log_stats("gateway", minutes=1440)
    assert stats["by_level"] and all(isinstance(v, int) for v in stats["by_level"].values())


def test_logging_templates_and_order() -> None:
    assert (
        logging_.template("ride 42 matched in 13ms for 5f6806bd-24c9-4225-a42b-5370cf9831f2")
        == "ride <n> matched in <n>ms for <uuid>"
    )
    entries = [
        {"service": "g", "level": "info", "line": "ok 1", "ts": "t1", "trace_id": None},
        {"service": "g", "level": "info", "line": "ok 2", "ts": "t2", "trace_id": None},
        {"service": "g", "level": "error", "line": "boom", "ts": "t3", "trace_id": None},
    ]
    groups = logging_.prune(entries)
    assert groups[0]["level"] == "error" and groups[1]["count"] == 2 and groups[1]["last"] == "t2"


def test_releases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        releases,
        "_http",
        client(
            "http://vitals",
            {
                "/api/releases": fixture("vitals_releases.json"),
                "/api/issues/VIT-1001": fixture("vitals_issue_vit1001.json"),
            },
        ),
    )
    tags = {"items": [{"tag": "v1.6.1"}, {"tag": "v1.5.2"}]}

    def fake_list(repo: str, limit: int = 15) -> dict[str, Any]:
        return tags

    monkeypatch.setattr(releases, "list_releases", fake_list)

    def prev(repo: str, ref: str) -> dict[str, Any]:
        return {"previous_release": "v1.5.2"}

    monkeypatch.setattr(releases.git_history, "previous_release", prev)

    def window(*_: object, **__: object) -> dict[str, Any]:
        return {"commits": [{"sha": "d1f5020"}]}

    monkeypatch.setattr(releases.git_history, "commits_between", window)
    adoption = releases.version_adoption()
    assert adoption["versions"][0]["version"] == "1.6.1"  # newest first
    lgfb = releases.last_good_and_first_bad("VIT-1001")
    assert (lgfb["first_bad"], lgfb["last_good"], lgfb["commits_in_window"]) == ("v1.6.1", "v1.5.2", 1)


def test_metrics_promql(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        metrics_profiles,
        "_prom",
        client("http://prom", {"/api/v1/query_range": fixture("prom_request_rate.json")}),
    )
    out = metrics_profiles.promql(
        "sum by (job) (rate(http_server_request_duration_seconds_count[5m]))", minutes=1440
    )
    assert out["total"] == 3 and {s["labels"]["job"] for s in out["items"]} == {
        "dispatch",
        "gateway",
        "payments",
    }
    assert all({"last", "min", "max", "avg"} <= set(s) for s in out["items"] if s["points"])
