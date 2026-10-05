"""bug-reports MCP server (BugDrop): in-app reports, their log rings, screenshots and UI-state timeline."""

from __future__ import annotations

from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP, Image

from debugassist.mcp_servers.common import cap, env, truncate, with_evidence

mcp = FastMCP("bug-reports", log_level="WARNING")
BUGDROP = env("BUGDROP_URL", "http://localhost:8200")
_http = httpx.Client(base_url=BUGDROP, timeout=15)
LOG_KINDS = ("network", "analytics", "console", "graphql", "ui_state", "perf")


def _get(path: str, **params: Any) -> Any:
    r = _http.get(path, params={k: v for k, v in params.items() if v is not None})
    r.raise_for_status()
    return r.json()


@mcp.tool()
def list_reports(
    app: str | None = None, since: str | None = None, limit: int = 20, offset: int = 0
) -> dict[str, Any]:
    """Recent bug reports (newest first): description, app version, device, city. `since` is ISO 8601."""
    rows = [
        {
            "id": r["id"],
            "created_at": r["created_at"],
            "description": truncate(r.get("description") or "", 300),
            "app": r.get("app"),
            "version": r.get("version"),
            "city": r.get("city"),
            "status": r.get("status"),
        }
        for r in _get("/api/reports", app_name=app, since=since, limit=200)
    ]
    return with_evidence("bugdrop", "reports", cap(rows, limit, offset))


@mcp.tool()
def get_report(report_id: str) -> dict[str, Any]:
    """One report: the user's words, app/device/city, flags and network at report time, log counts, files."""
    r = _get(f"/api/reports/{report_id}")
    keep = (
        "id",
        "created_at",
        "description",
        "app",
        "version",
        "session_id",
        "analytics_id",
        "device",
        "city",
    )
    out = {k: r.get(k) for k in keep}
    out |= {
        "route": r.get("route"),
        "flags": r.get("flags"),
        "network": r.get("network"),
        "log_counts": r.get("log_counts"),
        "files": [
            {k: f.get(k) for k in ("name", "kind", "content_type", "bytes")} for f in r.get("files", [])
        ],
    }
    return with_evidence("bugdrop", "report", out)


@mcp.tool()
def get_logs(
    report_id: str,
    kind: str,
    q: str | None = None,
    since: float | None = None,
    until: float | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Entries from one log ring (network, analytics, console, graphql, ui_state, perf), filtered by text
    (`q`) and epoch-seconds window. Network entries carry method, URL template, status and timing only."""
    if kind not in LOG_KINDS:
        return {"error": f"kind must be one of {LOG_KINDS}"}
    d = _get(f"/api/reports/{report_id}/logs", kind=kind, q=q, since=since, until=until, limit=500)
    page = cap(d.get("entries", []), limit, offset)
    return with_evidence("bugdrop", "logs", {"report_id": report_id, "log_kind": kind, **page})


@mcp.tool()
def get_screenshots(report_id: str) -> dict[str, Any]:
    """Screenshot metadata: the app's own screen (never the OS screen) and any images the user attached."""
    files = _get(f"/api/reports/{report_id}/screenshots")
    rows = [{k: f.get(k) for k in ("name", "kind", "content_type", "bytes", "original_name")} for f in files]
    return with_evidence("screenshot", "screenshots", {"report_id": report_id, "files": rows})


@mcp.tool()
def get_screenshot_image(report_id: str, name: str) -> Image:
    """The image itself, for vision-capable models (see get_screenshots for names)."""
    r = _http.get(f"/api/reports/{report_id}/files/{name}")
    r.raise_for_status()
    fmt = r.headers.get("content-type", "image/png").split("/")[-1]
    return Image(data=r.content, format=fmt)


@mcp.tool()
def get_ui_state_timeline(report_id: str) -> dict[str, Any]:
    """Visibility intervals and route changes before the report, with total and longest time hidden."""
    return with_evidence(
        "bugdrop",
        "ui_state_timeline",
        {"report_id": report_id, **_get(f"/api/reports/{report_id}/ui-state-timeline")},
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
