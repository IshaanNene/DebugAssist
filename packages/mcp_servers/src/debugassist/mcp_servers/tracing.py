"""tracing MCP server (Jaeger v2, query API v3): find traces and get them summarized, never raw.

The v3 API streams OTLP JSON, one document per chunk (a chunk can hold several traces), so spans are
grouped by trace id here. A trace summary gives the critical path, error spans and the slowest spans.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from debugassist.mcp_servers.common import cap, env, with_evidence

mcp = FastMCP("tracing", log_level="WARNING")
JAEGER = env("JAEGER_URL", "http://localhost:16686")
_http = httpx.Client(base_url=JAEGER, timeout=30)
HEALTH = ("/healthz", "/readyz", "/livez", "/metrics", "/health")


def _iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _spans(text: str) -> list[dict[str, Any]]:
    """Flatten OTLP JSON documents into spans tagged with their service."""
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        doc: dict[str, Any] = json.loads(line).get("result", {})
        for rs in doc.get("resourceSpans", []):
            attrs: dict[str, dict[str, Any]] = {
                a["key"]: a["value"] for a in rs.get("resource", {}).get("attributes", [])
            }
            service = str((attrs.get("service.name") or {}).get("stringValue", "?"))
            for ss in rs.get("scopeSpans", []):
                for sp in ss.get("spans", []):
                    start, end = int(sp["startTimeUnixNano"]), int(sp["endTimeUnixNano"])
                    status = sp.get("status", {}).get("code")
                    out.append(
                        {
                            "trace_id": sp["traceId"],
                            "span_id": sp["spanId"],
                            "parent": sp.get("parentSpanId") or None,
                            "service": service,
                            "name": sp.get("name", "?"),
                            "start": start,
                            "ms": round((end - start) / 1e6, 2),
                            "error": status in (2, "STATUS_CODE_ERROR"),
                            "attrs": {
                                a["key"]: next(iter(a["value"].values()), None)
                                for a in sp.get("attributes", [])
                                if a["key"]
                                in (
                                    "http.route",
                                    "http.status_code",
                                    "http.response.status_code",
                                    "graphql.operation.name",
                                    "db.statement",
                                    "exception.message",
                                )
                            },
                        }
                    )
    return out


def _group(spans: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    traces: dict[str, list[dict[str, Any]]] = {}
    for s in spans:
        traces.setdefault(s["trace_id"], []).append(s)
    return traces


def _overview(trace_id: str, spans: list[dict[str, Any]]) -> dict[str, Any]:
    roots = [s for s in spans if not s["parent"] or s["parent"] not in {x["span_id"] for x in spans}]
    root = min(roots or spans, key=lambda s: s["start"])
    return {
        "trace_id": trace_id,
        "root": f"{root['service']}: {root['name']}",
        "started": datetime.fromtimestamp(root["start"] / 1e9, UTC).isoformat(),
        "duration_ms": root["ms"],
        "spans": len(spans),
        "services": sorted({s["service"] for s in spans}),
        "errors": sum(s["error"] for s in spans),
    }


def _critical_path(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """From the root, follow the child that ends last at each level."""
    by_parent: dict[str | None, list[dict[str, Any]]] = {}
    ids = {s["span_id"] for s in spans}
    for s in spans:
        by_parent.setdefault(s["parent"] if s["parent"] in ids else None, []).append(s)
    path: list[dict[str, Any]] = []
    level = by_parent.get(None, [])
    while level:
        nxt = max(level, key=lambda s: s["start"] + s["ms"] * 1e6)
        path.append({k: nxt[k] for k in ("service", "name", "ms", "error")})
        level = by_parent.get(nxt["span_id"], [])
    return path


def _entry_operations(service: str, include_health_checks: bool) -> list[str]:
    """The service's server-side entry operations (where requests arrive), minus health checks."""
    r = _http.get("/api/v3/operations", params={"service": service, "span_kind": "server"})
    r.raise_for_status()
    names = sorted(
        {o["name"] for o in r.json().get("operations", []) if o.get("spanKind") in ("server", None)}
    )
    return [n for n in names if include_health_checks or not any(h in n for h in HEALTH)][:12]


@mcp.tool()
def find_traces(
    service: str,
    operation: str | None = None,
    lookback_minutes: int = 60,
    min_duration_ms: int | None = None,
    errors_only: bool = False,
    include_health_checks: bool = False,
    limit: int = 20,
) -> dict[str, Any]:
    """Recent traces through `service` (optionally an operation), newest first, as one-line overviews.
    Health-check traces (/healthz, /readyz, /metrics) are left out unless asked for."""
    now = datetime.now(UTC)
    base: dict[str, Any] = {
        "query.service_name": service,
        "query.start_time_min": _iso(now - timedelta(minutes=lookback_minutes)),
        "query.start_time_max": _iso(now),
        "query.search_depth": 100,
    }
    if min_duration_ms:
        base["query.duration_min"] = f"{min_duration_ms}ms"
    # Health checks fire every few seconds and would fill any "latest N" window, so search per real
    # entry operation instead of filtering afterwards.
    ops = [operation] if operation else _entry_operations(service, include_health_checks)
    spans: list[dict[str, Any]] = []
    for op in ops or [None]:
        params = {**base, **({"query.operation_name": op} if op else {})}
        r = _http.get("/api/v3/traces", params=params)
        if r.status_code == 404:
            continue
        r.raise_for_status()
        spans += _spans(r.text)
    rows = [_overview(tid, sp) for tid, sp in _group(spans).items()]
    if errors_only:
        rows = [t for t in rows if t["errors"]]
    if not include_health_checks:
        rows = [t for t in rows if not any(h in t["root"] for h in HEALTH)]
    rows.sort(key=lambda t: t["started"], reverse=True)
    return with_evidence("traces", "traces", {"service": service, **cap(rows, limit)})


@mcp.tool()
def get_trace(trace_id: str, slowest: int = 5) -> dict[str, Any]:
    """One trace summarized: overview, critical path, error spans and the slowest spans."""
    r = _http.get(f"/api/v3/traces/{trace_id}")
    r.raise_for_status()
    spans = _spans(r.text)
    if not spans:
        return {"error": f"trace {trace_id} not found"}
    errs = [{k: s[k] for k in ("service", "name", "ms", "attrs")} for s in spans if s["error"]]
    slow = sorted(spans, key=lambda s: s["ms"], reverse=True)[:slowest]
    return with_evidence(
        "traces",
        "trace",
        {
            **_overview(trace_id, spans),
            "critical_path": _critical_path(spans),
            "error_spans": errs[:10],
            "slowest_spans": [{k: s[k] for k in ("service", "name", "ms", "attrs")} for s in slow],
        },
    )


@mcp.tool()
def service_dependencies(lookback_hours: int = 24) -> dict[str, Any]:
    """Which service calls which, with call counts, over the lookback window."""
    end_ms = int(datetime.now(UTC).timestamp() * 1000)
    r = _http.get("/api/dependencies", params={"endTs": end_ms, "lookback": lookback_hours * 3_600_000})
    r.raise_for_status()
    edges = [
        {"parent": d["parent"], "child": d["child"], "calls": d["callCount"]}
        for d in r.json().get("data", [])
        if d["parent"] != d["child"]
    ]
    return with_evidence(
        "traces", "service_dependencies", {"edges": sorted(edges, key=lambda e: -e["calls"])}
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
