"""git-history MCP server: commits between releases, details, diff stats, bisect candidates.

Windows are hard-limited (pruned input, as in the talk: give the commit finder the last good and
first bad versions and history filtered to the relevant module, not the whole log).
"""

from __future__ import annotations

import re
import subprocess
from typing import Any

from mcp.server.fastmcp import FastMCP

from debugassist.mcp_servers.common import truncate, with_evidence
from debugassist.mcp_servers.repos import resolve

mcp = FastMCP("git-history", log_level="WARNING")
MAX_COMMITS = 50
REF = re.compile(r"^[\w./-]{1,100}$")


def _git(repo: str, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=resolve(repo), capture_output=True, text=True)
    if out.returncode:
        raise ValueError(out.stderr.strip()[:300])
    return out.stdout


def _check_ref(ref: str) -> None:
    if not REF.match(ref) or ".." in ref:
        raise ValueError(f"invalid ref {ref!r}")


@mcp.tool()
def list_tags(repo: str, limit: int = 20) -> dict[str, Any]:
    """Release tags, newest first, with dates."""
    out = _git(repo, "tag", "--sort=-creatordate", "--format=%(refname:short)|%(creatordate:iso-strict)")
    rows = [dict(zip(("tag", "date"), ln.split("|"), strict=False)) for ln in out.splitlines()[:limit]]
    return with_evidence("git", "tags", {"repo": repo, "tags": rows})


@mcp.tool()
def previous_release(repo: str, ref: str) -> dict[str, Any]:
    """The nearest release tag in `ref`'s own history before it (the last good release)."""
    _check_ref(ref)
    resolve(repo)  # an unknown repo is an error, not "no previous release"
    try:
        tag = _git(repo, "describe", "--tags", "--abbrev=0", f"{ref}^").strip()
    except ValueError:
        tag = None
    return with_evidence("git", "previous_release", {"repo": repo, "ref": ref, "previous_release": tag})


@mcp.tool()
def commits_between(
    repo: str, last_good: str, first_bad: str, path_filters: list[str] | None = None
) -> dict[str, Any]:
    """Commits in (last_good, first_bad], optionally only those touching path prefixes (e.g. ['src/notifications'])."""
    _check_ref(last_good)
    _check_ref(first_bad)
    args = ["log", f"--max-count={MAX_COMMITS}", "--format=%H|%an|%aI|%s", f"{last_good}..{first_bad}"]
    if path_filters:
        args += ["--", *path_filters]
    rows = [
        dict(zip(("sha", "author", "date", "subject"), ln.split("|", 3), strict=False))
        for ln in _git(repo, *args).splitlines()
    ]
    for r in rows:
        r["sha"] = r["sha"][:12]
    return with_evidence(
        "git",
        "commits",
        {
            "repo": repo,
            "range": f"{last_good}..{first_bad}",
            "path_filters": path_filters or [],
            "commits": rows,
        },
    )


@mcp.tool()
def commit_details(repo: str, sha: str, max_diff_chars: int = 8000) -> dict[str, Any]:
    """Message, author, files and (truncated) diff of a commit."""
    _check_ref(sha)
    meta = _git(repo, "show", "-s", "--format=%H%n%an <%ae>%n%aI%n%B", sha).split("\n", 3)
    stat = _git(repo, "show", "--stat", "--format=", sha).strip()
    diff = _git(
        repo, "show", "--format=", "--unified=3", sha, "--", ".", ":(exclude)*.lock", ":(exclude)*lock.yaml"
    )
    return with_evidence(
        "git",
        "commit",
        {
            "repo": repo,
            "sha": meta[0][:12],
            "author": meta[1],
            "date": meta[2],
            "message": meta[3].strip(),
            "stat": stat,
            "diff": truncate(diff, max_diff_chars),
        },
    )


@mcp.tool()
def diff_stats(repo: str, from_ref: str, to_ref: str) -> dict[str, Any]:
    """Files changed between two refs with insertions/deletions."""
    _check_ref(from_ref)
    _check_ref(to_ref)
    rows: list[dict[str, str]] = []
    for ln in _git(repo, "diff", "--numstat", f"{from_ref}..{to_ref}").splitlines():
        add, delete, path = ln.split("\t", 2)
        rows.append({"path": path, "added": add, "deleted": delete})
    return with_evidence(
        "git", "diff_stats", {"repo": repo, "range": f"{from_ref}..{to_ref}", "files": rows[:200]}
    )


@mcp.tool()
def bisect_candidates(repo: str, last_good: str, first_bad: str, suspect_paths: list[str]) -> dict[str, Any]:
    """Rank commits in the window by how directly they touch the suspect files (e.g. files from the stack trace)."""
    _check_ref(last_good)
    _check_ref(first_bad)
    out = _git(
        repo,
        "log",
        f"--max-count={MAX_COMMITS}",
        "--format=@@%H|%an|%s",
        "--name-only",
        f"{last_good}..{first_bad}",
    )
    ranked: list[dict[str, Any]] = []
    for block in out.split("@@")[1:]:
        head, *files = [ln for ln in block.splitlines() if ln.strip()]
        sha, author, subject = head.split("|", 2)
        exact = [f for f in files if f in suspect_paths]
        near = [
            f
            for f in files
            if f not in exact and any(f.rsplit("/", 1)[0] == s.rsplit("/", 1)[0] for s in suspect_paths)
        ]
        score = 3 * len(exact) + len(near)
        if score:
            ranked.append(
                {
                    "sha": sha[:12],
                    "author": author,
                    "subject": subject,
                    "score": score,
                    "touches": exact + near,
                }
            )
    ranked.sort(key=lambda r: -r["score"])
    return with_evidence(
        "git",
        "bisect_candidates",
        {"repo": repo, "range": f"{last_good}..{first_bad}", "candidates": ranked[:10]},
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
