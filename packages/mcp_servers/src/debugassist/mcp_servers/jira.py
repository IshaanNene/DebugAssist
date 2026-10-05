"""jira MCP server: read tickets, and create / comment / link / transition them (writes policy-gated and
dry-run by default). Jira Cloud when credentials are set, otherwise the local mock with the same tools."""

from __future__ import annotations

import os
from functools import cache
from typing import Any

from mcp.server.fastmcp import FastMCP

from debugassist.core.settings import Integration, Mode, get_settings
from debugassist.integrations.jira import Jira, JiraCloud, JiraMock
from debugassist.mcp_servers.common import gated_write, truncate, with_evidence

mcp = FastMCP("jira", log_level="WARNING")


@cache
def client() -> Jira:
    s = get_settings()
    if s.mode(Integration.JIRA) is Mode.LIVE and s.jira_base_url and s.jira_email and s.jira_api_key:
        project = os.environ.get("JIRA_PROJECT_KEY", "SCRUM")
        return JiraCloud(s.jira_base_url, s.jira_email, s.jira_api_key.get_secret_value(), project)
    return JiraMock()


@mcp.tool()
def get_issue(key: str) -> dict[str, Any]:
    """A ticket as Jira holds it: status, priority, labels, links and the latest comments."""
    t = client().snapshot(key)
    t["comments"] = [{**c, "text": truncate(c["text"], 800)} for c in t.get("comments", [])][-5:]
    return with_evidence("jira", "issue", t)


@mcp.tool()
def find_open_issue(label: str) -> dict[str, Any]:
    """The newest open ticket carrying `label` (e.g. the Vitals issue label), if any — for dedup."""
    t = client().find_open(label)
    return with_evidence("jira", "find_open", {"label": label, "issue": t.model_dump() if t else None})


@mcp.tool()
def create_issue(
    summary: str,
    description: str,
    priority: str = "P2",
    labels: list[str] | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Create a ticket (write; policy-gated, dry-run unless dry_run=false and the policy allows)."""
    detail = {"summary": summary[:120], "priority": priority, "labels": labels or []}
    return gated_write(
        "jira.create_issue",
        detail,
        lambda: client().create(summary, [("para", description)], priority, labels or []).model_dump(),
        dry_run=dry_run,
    )


@mcp.tool()
def add_comment(key: str, text: str, dry_run: bool = True) -> dict[str, Any]:
    """Comment on a ticket (write; policy-gated, dry-run by default)."""
    return gated_write(
        "jira.comment",
        {"key": key, "chars": len(text)},
        lambda: client().comment(key, [("para", text)]),
        dry_run=dry_run,
    )


@mcp.tool()
def link_pr(key: str, url: str, title: str, dry_run: bool = True) -> dict[str, Any]:
    """Attach a pull request link to a ticket (write; idempotent; policy-gated, dry-run by default)."""
    return gated_write(
        "jira.link", {"key": key, "url": url}, lambda: client().link(key, url, title), dry_run=dry_run
    )


@mcp.tool()
def transition(key: str, status: str, dry_run: bool = True) -> dict[str, Any]:
    """Move a ticket to a status by name, e.g. "In Progress" or "In Review" (write; dry-run by default)."""
    return gated_write(
        "jira.transition",
        {"key": key, "status": status},
        lambda: client().transition(key, status),
        dry_run=dry_run,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
