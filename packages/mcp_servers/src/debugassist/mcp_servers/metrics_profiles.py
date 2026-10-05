"""metrics-profiles MCP server ("production debugging"): PromQL, service profiles, and a session's
client-side performance samples (CPU while hidden, timer wakeups, long tasks, memory)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from debugassist.mcp_servers.common import cap, env, with_evidence

mcp = FastMCP("metrics-profiles", log_level="WARNING")
PROM = env("PROMETHEUS_URL", "http://localhost:9090")
VITALS = env("VITALS_URL", "http://localhost:8100")
_prom = httpx.Client(base_url=PROM, timeout=20)
_vitals = httpx.Client(base_url=VITALS, timeout=15)
PERF_KINDS = {"perf", "hang", "jank", "background_cpu", "memory"}


def _range(query: str, minutes: int, step_s: int) -> list[dict[str, Any]]:
    end = datetime.now(UTC).timestamp()
    r = _prom.get(
        "/api/v1/query_range",
        params={"query": query, "start": end - minutes * 60, "end": end, "step": step_s},
    )
    r.raise_for_status()
    body = r.json()
    if body.get("status") != "success":
        raise ValueError(body.get("error", "query failed"))
    return body["data"]["result"]


def _summary(series: dict[str, Any]) -> dict[str, Any]:
    vals = [float(v) for _, v in series.get("values", []) if v not in ("NaN", "+Inf", "-Inf")]
    labels = {k: v for k, v in series["metric"].items() if not k.startswith(("process_", "host_", "otel_"))}
    if not vals:
        return {"labels": labels, "points": 0}
    return {
        "labels": labels,
        "points": len(vals),
        "last": round(vals[-1], 4),
        "min": round(min(vals), 4),
        "max": round(max(vals), 4),
        "avg": round(sum(vals) / len(vals), 4),
    }


@mcp.tool()
def promql(query: str, minutes: int = 60, step_seconds: int = 60, limit: int = 20) -> dict[str, Any]:
    """Run a PromQL range query; each series comes back summarized (last, min, max, avg), not as raw points."""
    rows = [_summary(s) for s in _range(query, minutes, max(step_seconds, 15))]
    return with_evidence("metrics", "promql", {"query": query, "minutes": minutes, **cap(rows, limit)})


def _scalar(query: str, minutes: int) -> float | None:
    rows = _range(query, minutes, max(60, minutes * 60 // 30))
    vals = [float(v) for s in rows for _, v in s.get("values", [])[-1:] if v not in ("NaN", "+Inf", "-Inf")]
    return round(sum(vals), 4) if vals else None


@mcp.tool()
def service_profile(service: str, minutes: int = 60) -> dict[str, Any]:
    """A service's vital signs over the window: request rate, p95 latency, 5xx share, slowest routes, memory."""
    sel = f'job="{service}"'
    w = "5m"
    profile: dict[str, Any] = {
        "service": service,
        "minutes": minutes,
        "requests_per_s": _scalar(
            f"sum(rate(http_server_request_duration_seconds_count{{{sel}}}[{w}]))", minutes
        ),
        "p95_latency_ms": _scalar(
            f"1000 * histogram_quantile(0.95, sum by (le) (rate(http_server_request_duration_seconds_bucket{{{sel}}}[{w}])))",
            minutes,
        ),
        "error_5xx_share": _scalar(
            f'sum(rate(http_server_request_duration_seconds_count{{{sel},http_response_status_code=~"5.."}}[{w}]))'
            f" / sum(rate(http_server_request_duration_seconds_count{{{sel}}}[{w}]))",
            minutes,
        ),
        "heap_bytes": _scalar(f"sum(v8js_memory_heap_used_bytes{{{sel}}})", minutes)
        or _scalar(f"sum(go_memstats_heap_inuse_bytes{{{sel}}})", minutes),
    }
    routes = _range(
        f"1000 * histogram_quantile(0.95, sum by (le, http_route) (rate(http_server_request_duration_seconds_bucket{{{sel}}}[{w}])))",
        minutes,
        max(60, minutes * 60 // 30),
    )
    slow = sorted(
        ({"route": s["metric"].get("http_route"), "p95_ms": _summary(s).get("last")} for s in routes),
        key=lambda r: -(r["p95_ms"] or 0),
    )
    profile["slowest_routes"] = [r for r in slow if r["route"]][:5]
    return with_evidence("metrics", "service_profile", profile)


@mcp.tool()
def session_perf(session_id: str) -> dict[str, Any]:
    """Client performance samples from one session (Vitals): CPU busy while hidden, timer wakeups per
    second, long tasks, hangs, memory — the evidence behind battery and jank reports."""
    r = _vitals.get(f"/api/sessions/{session_id}")
    r.raise_for_status()
    s = r.json()
    samples = [
        {"ts": e.get("ts"), "kind": e.get("kind"), "title": e.get("title"), "perf": e.get("perf")}
        for e in s.get("events", [])
        if e.get("kind") in PERF_KINDS or e.get("perf")
    ]
    meta = {
        k: s.get(k)
        for k in ("id", "app", "version", "os", "browser", "device", "city", "flags", "started_at")
    }
    return with_evidence("metrics", "session_perf", {**meta, **cap(samples, 30)})


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
