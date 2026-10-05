"""Record live responses from the local stack as fixtures for the MCP server tests (run by hand):

    uv run --no-sync python packages/mcp_servers/tests/fixtures/record_live.py

Each fixture is the raw response body of one endpoint, so the tests replay exactly what the services
returned. Large bodies are trimmed to keep the repo small.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

OUT = Path(__file__).parent / "live"
NOW = datetime.now(UTC)


def iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def save(name: str, url: str, params: dict[str, Any] | None = None, *, lines: int | None = None) -> str:
    r = httpx.get(url, params=params, timeout=30)
    r.raise_for_status()
    body = r.text if lines is None else "\n".join(r.text.splitlines()[:lines])
    (OUT / name).write_text(body if body.endswith("\n") else body + "\n")
    print(f"{name}: {len(body)} bytes")
    return r.text


def main() -> None:
    OUT.mkdir(exist_ok=True)
    save("bugdrop_reports.json", "http://localhost:8200/api/reports")
    save("bugdrop_report.json", "http://localhost:8200/api/reports/BD-1001")
    save(
        "bugdrop_logs_network.json",
        "http://localhost:8200/api/reports/BD-1001/logs",
        {"kind": "network", "limit": 500},
    )
    save("bugdrop_screenshots.json", "http://localhost:8200/api/reports/BD-1001/screenshots")
    save("bugdrop_timeline.json", "http://localhost:8200/api/reports/BD-1001/ui-state-timeline")
    save("incidents_dependencies.json", "http://localhost:8300/api/dependencies")
    save(
        "jaeger_operations_dispatch.json",
        "http://localhost:16686/api/v3/operations",
        {"service": "dispatch", "span_kind": "server"},
    )
    traces = save(
        "jaeger_traces_dispatch_places.ndjson",
        "http://localhost:16686/api/v3/traces",
        {
            "query.service_name": "dispatch",
            "query.operation_name": "GET /places",
            "query.start_time_min": iso(NOW - timedelta(hours=24)),
            "query.start_time_max": iso(NOW),
            "query.search_depth": 3,
        },
        lines=1,
    )
    tid = json.loads(traces.splitlines()[0])["result"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0][
        "traceId"
    ]
    save("jaeger_trace.ndjson", f"http://localhost:16686/api/v3/traces/{tid}")
    save(
        "jaeger_dependencies.json",
        "http://localhost:16686/api/dependencies",
        {"endTs": int(NOW.timestamp() * 1000), "lookback": 86_400_000},
    )
    end_ns = int(NOW.timestamp() * 1e9)
    save(
        "loki_query_range_gateway.json",
        "http://localhost:3100/loki/api/v1/query_range",
        {
            "query": '{service_name="gateway"}',
            "start": end_ns - 86_400 * 10**9,
            "end": end_ns,
            "limit": 40,
            "direction": "backward",
        },
    )
    save(
        "loki_stats_gateway.json",
        "http://localhost:3100/loki/api/v1/query",
        {"query": 'sum by (detected_level) (count_over_time({service_name="gateway"}[1440m]))'},
    )
    save("vitals_releases.json", "http://localhost:8100/api/releases", {"app": "miniride-client"})
    save("vitals_issue_vit1001.json", "http://localhost:8100/api/issues/VIT-1001")
    end = NOW.timestamp()
    save(
        "prom_request_rate.json",
        "http://localhost:9090/api/v1/query_range",
        {
            "query": "sum by (job) (rate(http_server_request_duration_seconds_count[5m]))",
            "start": end - 86_400,
            "end": end,
            "step": 3600,
        },
    )


if __name__ == "__main__":
    main()
