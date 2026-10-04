"""crash-analytics MCP server (Vitals): issues, crash groups, sessions, distributions."""

from __future__ import annotations

from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from debugassist.mcp_servers.common import cap, env, with_evidence

mcp = FastMCP("crash-analytics", log_level="WARNING")
VITALS = env("VITALS_URL", "http://localhost:8100")
_http = httpx.Client(base_url=VITALS, timeout=15)


def _get(path: str, **params: Any) -> Any:
    r = _http.get(path, params={k: v for k, v in params.items() if v is not None})
    r.raise_for_status()
    return r.json()


def _slim_event(e: dict[str, Any], frames: int = 12) -> dict[str, Any]:
    out = {
        k: e.get(k)
        for k in (
            "id",
            "kind",
            "version",
            "session_id",
            "ts",
            "title",
            "culprit",
            "flags",
            "device",
            "trace_id",
        )
    }
    if e.get("frames") is not None:
        out["stack"] = [
            f"{f['function']} ({f['file']}:{f.get('line')})" + ("" if f.get("in_app", True) else " [lib]")
            for f in reversed(e["frames"][-frames:])
        ]
        out["error"] = e.get("error", {}) and {k: e["error"].get(k) for k in ("type", "message")}
        out["symbolicated"] = e.get("symbolicated")
    if e.get("perf"):
        out["perf"] = e["perf"]
    return out


@mcp.tool()
def list_issues(status: str | None = "open", app: str | None = None, limit: int = 20) -> dict[str, Any]:
    """Open Vitals issues (crash/exception/hang/jank/perf groups) with counts and versions."""
    rows = [
        {
            "id": i["id"],
            "title": i["title"],
            "kind": i["kind"],
            "app": i["app"],
            "status": i["status"],
            "reason": i["reason"],
            "events": i["group"]["count"],
            "first_version": i["group"]["first_version"],
            "last_version": i["group"]["last_version"],
            "fingerprint": i["fingerprint"],
            "opened_at": i["opened_at"],
        }
        for i in _get("/api/issues", status=status, app=app, limit=100)
    ]
    return with_evidence("vitals", "issues", cap(rows, limit))


@mcp.tool()
def get_issue(issue_id: str) -> dict[str, Any]:
    """One issue with its group and the latest event (symbolicated stack, flags, device)."""
    d = _get(f"/api/issues/{issue_id}")
    latest = d.get("latest_event")
    return with_evidence(
        "vitals",
        "issue",
        {
            "id": d["id"],
            "title": d["title"],
            "kind": d["kind"],
            "app": d["app"],
            "status": d["status"],
            "reason": d["reason"],
            "fingerprint": d["fingerprint"],
            "group": d["group"],
            "latest_event": _slim_event(latest) if latest else None,
        },
    )


@mcp.tool()
def get_crash_group(fingerprint: str, events: int = 5) -> dict[str, Any]:
    """A crash group with recent events (stacks, flags, device) and the latest event's breadcrumbs."""
    group = _get(f"/api/groups/{fingerprint}")
    evs = _get(f"/api/groups/{fingerprint}/events", limit=events, full=True)
    crumbs: list[Any] = evs[0].get("breadcrumbs", [])[-25:] if evs else []
    return with_evidence(
        "vitals",
        "crash_group",
        {"group": group, "events": [_slim_event(e) for e in evs], "breadcrumbs_latest": crumbs},
    )


@mcp.tool()
def get_session(session_id: str) -> dict[str, Any]:
    """A session: app version, device, city, locale, flag exposures, and its events."""
    return with_evidence("vitals", "session", _get(f"/api/sessions/{session_id}"))


@mcp.tool()
def distribution(fingerprint: str, by: str = "version") -> dict[str, Any]:
    """Affected vs all sessions by version, os, browser, device, city, locale or flag:<name>."""
    return with_evidence("vitals", "distribution", _get(f"/api/groups/{fingerprint}/distribution", by=by))


@mcp.tool()
def flag_exposure(fingerprint: str) -> dict[str, Any]:
    """For each feature flag: exposure among all sessions vs among affected sessions, and crash rates."""
    return with_evidence(
        "vitals",
        "flag_exposure",
        {"fingerprint": fingerprint, "flags": _get(f"/api/groups/{fingerprint}/flags")},
    )


@mcp.tool()
def crash_rate_timeseries(fingerprint: str, bucket_s: int = 300) -> dict[str, Any]:
    """Event counts per time bucket, split by app version."""
    return with_evidence(
        "vitals",
        "timeseries",
        {
            "fingerprint": fingerprint,
            "series": _get(f"/api/groups/{fingerprint}/timeseries", bucket_s=bucket_s),
        },
    )


@mcp.tool()
def releases(app: str = "miniride-client") -> dict[str, Any]:
    """Versions seen in sessions with adoption share and first/last seen."""
    return with_evidence("vitals", "releases", {"app": app, "versions": _get("/api/releases", app=app)})


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
