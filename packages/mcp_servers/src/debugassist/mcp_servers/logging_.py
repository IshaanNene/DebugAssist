"""logging MCP server (Loki): log queries pruned server-side — never raw dumps.

Pruning: collapse repeats into templates (numbers, ids and hashes masked) with counts and first/last
timestamps, put errors and warnings first, then cap the result size.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from debugassist.mcp_servers.common import cap, env, truncate, with_evidence

mcp = FastMCP("logging", log_level="WARNING")
LOKI = env("LOKI_URL", "http://localhost:3100")
_http = httpx.Client(base_url=LOKI, timeout=30)
LEVEL_RANK = {
    "fatal": 0,
    "critical": 0,
    "error": 1,
    "warn": 2,
    "warning": 2,
    "info": 3,
    "debug": 4,
    "trace": 5,
}
_MASKS = [
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "<uuid>"),
    (re.compile(r"\b[0-9a-f]{12,}\b", re.I), "<hex>"),
    (re.compile(r"(?<![A-Za-z_])\d+(\.\d+)?"), "<n>"),  # also 13ms, 200OK; keeps routeV2, http2
]


def template(line: str) -> str:
    for rx, repl in _MASKS:
        line = rx.sub(repl, line)
    return line.strip()


def _selector(service: str | None, logql: str | None, contains: str | None, level: str | None) -> str:
    if logql:
        return logql
    if not service:
        raise ValueError("pass service or logql")
    q = f'{{service_name="{service}"}}'
    if level:
        q += f' | detected_level="{level}"'
    if contains:
        q += f' |= "{contains.replace(chr(34), "")}"'
    return q


def _window(minutes: int, around: str | None = None) -> tuple[str, str]:
    """The last `minutes`, or `minutes` centred on `around` (ISO 8601) when given."""
    if around:
        mid = int(datetime.fromisoformat(around.replace("Z", "+00:00")).timestamp() * 1e9)
        half = minutes * 30 * 10**9
        return str(mid - half), str(mid + half)
    end = int(datetime.now(UTC).timestamp() * 1e9)
    return str(end - minutes * 60 * 10**9), str(end)


def _entries(query: str, minutes: int, raw_limit: int, around: str | None = None) -> list[dict[str, Any]]:
    start, end = _window(minutes, around)
    r = _http.get(
        "/loki/api/v1/query_range",
        params={"query": query, "start": start, "end": end, "limit": raw_limit, "direction": "backward"},
    )
    r.raise_for_status()
    out: list[dict[str, Any]] = []
    for stream in r.json()["data"]["result"]:
        labels = stream.get("stream", {})
        for ts, line in stream.get("values", []):
            out.append(
                {
                    "ts": datetime.fromtimestamp(int(ts) / 1e9, UTC).isoformat(),
                    "service": labels.get("service_name"),
                    "level": (labels.get("detected_level") or labels.get("level") or "unknown").lower(),
                    "trace_id": labels.get("trace_id") or labels.get("traceid"),
                    "line": line,
                }
            )
    return out


def prune(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse repeats by template; errors first, then by count."""
    groups: dict[tuple[str | None, str, str], dict[str, Any]] = {}
    for e in entries:
        key = (e["service"], e["level"], template(e["line"]))
        g = groups.get(key)
        if g is None:
            groups[key] = {
                "service": e["service"],
                "level": e["level"],
                "example": truncate(e["line"], 400),
                "count": 1,
                "first": e["ts"],
                "last": e["ts"],
                "trace_id": e["trace_id"],
            }
        else:
            g["count"] += 1
            g["first"], g["last"] = min(g["first"], e["ts"]), max(g["last"], e["ts"])
    return sorted(groups.values(), key=lambda g: (LEVEL_RANK.get(g["level"], 3), -g["count"]))


@mcp.tool()
def query_logs(
    service: str | None = None,
    contains: str | None = None,
    level: str | None = None,
    logql: str | None = None,
    minutes: int = 60,
    limit: int = 30,
    around: str | None = None,
) -> dict[str, Any]:
    """Logs for a service (or a raw LogQL selector), collapsed into repeated-line groups with counts and
    first/last times, errors first. Filter with `contains` (substring) and `level` (error, warn, info).
    The window is the last `minutes`, or `minutes` centred on `around` (ISO time of an event)."""
    query = _selector(service, logql, contains, level)
    entries = _entries(query, minutes, raw_limit=2000, around=around)
    groups = prune(entries)
    return with_evidence(
        "logs",
        "log_groups",
        {
            "query": query,
            "minutes": minutes,
            "around": around,
            "lines_scanned": len(entries),
            **cap(groups, limit),
        },
    )


@mcp.tool()
def log_stats(service: str, minutes: int = 60) -> dict[str, Any]:
    """Line counts by level for a service over the window."""
    r = _http.get(
        "/loki/api/v1/query",
        params={
            "query": f'sum by (detected_level) (count_over_time({{service_name="{service}"}}[{minutes}m]))'
        },
    )
    r.raise_for_status()
    counts = {
        (res["metric"].get("detected_level") or "unknown"): int(float(res["value"][1]))
        for res in r.json()["data"]["result"]
    }
    return with_evidence("logs", "log_stats", {"service": service, "minutes": minutes, "by_level": counts})


@mcp.tool()
def log_patterns(service: str, minutes: int = 60, top: int = 15) -> dict[str, Any]:
    """The most frequent line templates for a service — a quick picture of what it is doing."""
    entries = _entries(_selector(service, None, None, None), minutes, raw_limit=3000)
    counts = Counter(template(e["line"]) for e in entries)
    rows = [{"template": truncate(t, 300), "count": c} for t, c in counts.most_common(top)]
    return with_evidence(
        "logs", "log_patterns", {"service": service, "lines_scanned": len(entries), "patterns": rows}
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
