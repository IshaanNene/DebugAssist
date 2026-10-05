"""incidents MCP server: declared incidents and third-party dependency status (is something already on fire?)."""

from __future__ import annotations

from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from debugassist.mcp_servers.common import cap, env, with_evidence

mcp = FastMCP("incidents", log_level="WARNING")
INCIDENTS = env("INCIDENTS_URL", "http://localhost:8300")
_http = httpx.Client(base_url=INCIDENTS, timeout=15)


def _get(path: str, **params: Any) -> Any:
    r = _http.get(path, params={k: v for k, v in params.items() if v is not None})
    r.raise_for_status()
    return r.json()


def _slim(i: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "id",
        "title",
        "severity",
        "status",
        "services",
        "owner_team",
        "started_at",
        "resolved_at",
        "summary",
    )
    return {k: i.get(k) for k in keep}


@mcp.tool()
def list_active_incidents(service: str | None = None, limit: int = 20) -> dict[str, Any]:
    """Incidents not yet resolved, optionally only those touching `service`."""
    rows = [_slim(i) for i in _get("/api/incidents") if i.get("status") != "resolved"]
    if service:
        rows = [i for i in rows if service in (i.get("services") or [])]
    return with_evidence("incident", "active_incidents", cap(rows, limit))


@mcp.tool()
def incident_details(incident_id: str) -> dict[str, Any]:
    """One incident with its timeline of updates."""
    i = _get(f"/api/incidents/{incident_id}")
    return with_evidence("incident", "incident", {**_slim(i), "updates": (i.get("updates") or [])[-20:]})


@mcp.tool()
def dependency_status(name: str | None = None) -> dict[str, Any]:
    """Status of third-party dependencies (maps, payments, push, SMS…): operational, degraded or outage."""
    deps: dict[str, Any] = _get("/api/dependencies")
    if name:
        deps = {name: deps.get(name, {"status": "unknown"})}
    degraded = sorted(n for n, d in deps.items() if d.get("status") != "operational")
    return with_evidence("incident", "dependencies", {"dependencies": deps, "not_operational": degraded})


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
