"""releases MCP server: versions, adoption, release diffs, rollouts, and last-good / first-bad for an issue.

last_good_and_first_bad is the pruned input the commit finder needs (the talk: hand it the last clean
version and the first bad one, never the whole history).
"""

from __future__ import annotations

from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from debugassist.mcp_servers import feature_flags, git_history
from debugassist.mcp_servers.common import cap, env, with_evidence

mcp = FastMCP("releases", log_level="WARNING")
VITALS = env("VITALS_URL", "http://localhost:8100")
_http = httpx.Client(base_url=VITALS, timeout=15)
APP_REPO = {
    "miniride-client": "miniride-client",
    "gateway": "miniride-services",
    "dispatch": "miniride-services",
    "payments": "miniride-services",
}


def _vkey(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split(".") if x.isdigit())


@mcp.tool()
def version_adoption(app: str = "miniride-client") -> dict[str, Any]:
    """Share of sessions on each version of an app (from Vitals sessions), newest version first."""
    r = _http.get("/api/releases", params={"app": app})
    r.raise_for_status()
    rows = sorted(r.json(), key=lambda x: _vkey(x["version"]), reverse=True)
    return with_evidence("releases", "version_adoption", {"app": app, "versions": rows})


@mcp.tool()
def list_releases(repo: str, limit: int = 15) -> dict[str, Any]:
    """Release tags of a repository, newest first, with dates and subjects."""
    out = git_history.run_git(
        repo,
        "for-each-ref",
        "--sort=-creatordate",
        "--format=%(refname:short)\t%(creatordate:iso-strict)\t%(subject)",
        "refs/tags",
    )
    rows = [
        dict(zip(("tag", "date", "subject"), ln.split("\t", 2), strict=False))
        for ln in out.splitlines()
        if ln
    ]
    return with_evidence("releases", "releases", {"repo": repo, **cap(rows, limit)})


@mcp.tool()
def release_diff(repo: str, from_ref: str, to_ref: str, paths: list[str] | None = None) -> dict[str, Any]:
    """What changed between two releases: commits (optionally only under `paths`) and file stats."""
    commits = git_history.commits_between(repo, from_ref, to_ref, paths)
    stats = git_history.diff_stats(repo, from_ref, to_ref)
    return with_evidence(
        "releases",
        "release_diff",
        {
            "repo": repo,
            "range": f"{from_ref}..{to_ref}",
            "commits": commits.get("commits", []),
            "files": stats.get("files", []),
        },
    )


@mcp.tool()
def rollout_status() -> dict[str, Any]:
    """Every feature flag's current state and gradual-rollout percentage."""
    flags = feature_flags.list_flags()
    return with_evidence("releases", "rollout_status", {"flags": flags.get("flags", [])})


@mcp.tool()
def last_good_and_first_bad(issue_id: str) -> dict[str, Any]:
    """For a Vitals issue: the first version it appeared in and the release before it (the last good one),
    with the commit window between them — the narrowed input for finding the offending commit."""
    r = _http.get(f"/api/issues/{issue_id}")
    r.raise_for_status()
    issue = r.json()
    app = issue.get("app", "miniride-client")
    first_bad = f"v{issue['group']['first_version']}"
    repo = APP_REPO.get(app, "miniride-client")
    tags = {t["tag"] for t in list_releases(repo, limit=200)["items"]}
    out: dict[str, Any] = {
        "issue": issue_id,
        "app": app,
        "repo": repo,
        "first_bad": first_bad,
        "last_good": None,
    }
    if first_bad in tags:
        out["last_good"] = git_history.previous_release(repo, first_bad).get("previous_release")
    if out["last_good"]:
        window = git_history.commits_between(repo, out["last_good"], first_bad, None)
        out["commits_in_window"] = len(window.get("commits", []))
    else:
        out["note"] = f"{first_bad} is not a tag in {repo}, or it has no earlier release"
    return with_evidence("releases", "last_good_first_bad", out)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
