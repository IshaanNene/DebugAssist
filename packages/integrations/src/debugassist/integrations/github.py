"""GitHub: push bot branches and open pull requests (REST), or record them locally in mock mode."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import httpx
from pydantic import BaseModel

from debugassist.core.policy import ROOT
from debugassist.core.workspace import Workspace


class PullRequest(BaseModel):
    number: int
    url: str
    head: str
    base: str
    draft: bool
    mode: str


class RateLimited(RuntimeError):
    """GitHub said to stop: wait `wait_s` seconds before the next call."""

    def __init__(self, wait_s: float, why: str) -> None:
        super().__init__(f"GitHub rate limit ({why}): retry in {wait_s:.0f} s")
        self.wait_s = wait_s


def check_rate_limit(r: httpx.Response, now: float | None = None) -> None:
    """An httpx response hook: a primary (`X-RateLimit-Remaining: 0`) or secondary (`Retry-After`) limit becomes
    RateLimited with how long to wait, instead of an HTTP error the caller would retry at once and make worse."""
    if r.status_code not in (403, 429):
        return
    if (after := r.headers.get("retry-after")) is not None:
        raise RateLimited(float(after), "secondary")
    if r.headers.get("x-ratelimit-remaining") == "0":
        reset = float(r.headers.get("x-ratelimit-reset") or 0)
        raise RateLimited(max(0.0, reset - (time.time() if now is None else now)), "primary")


class GitHub(Protocol):
    def remote_branch_exists(self, repo: str, branch: str) -> bool: ...
    def push(self, worktree: Path, branch: str) -> None: ...
    def open_pr(self, repo: str, head: str, base: str, title: str, body: str, draft: bool) -> PullRequest: ...
    def comment(self, repo: str, number: int, body: str) -> None: ...
    def merged(self, repo: str, number: int) -> bool | None: ...


class GitHubLive:
    def __init__(self, token: str) -> None:
        self.http = httpx.Client(
            base_url="https://api.github.com",
            timeout=30,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            event_hooks={"response": [check_rate_limit]},
        )

    def remote_branch_exists(self, repo: str, branch: str) -> bool:
        return self.http.get(f"/repos/{repo}/branches/{branch}").status_code == 200

    def push(self, worktree: Path, branch: str) -> None:
        # Uses the developer's configured git remote credentials (the token never enters the sandbox).
        Workspace(worktree).git("push", "-q", "-f", "origin", f"HEAD:refs/heads/{branch}", check=True)

    def open_pr(self, repo: str, head: str, base: str, title: str, body: str, draft: bool) -> PullRequest:
        existing = self.http.get(
            f"/repos/{repo}/pulls", params={"head": f"{repo.split('/')[0]}:{head}", "state": "open"}
        ).json()
        if existing:
            pr = existing[0]
            self.http.patch(
                f"/repos/{repo}/pulls/{pr['number']}", json={"title": title, "body": body}
            ).raise_for_status()
            if bool(pr.get("draft")) != draft:  # REST cannot change draft state; GraphQL can
                self._set_draft(pr["node_id"], draft)
        else:
            r = self.http.post(
                f"/repos/{repo}/pulls",
                json={"title": title, "head": head, "base": base, "body": body, "draft": draft},
            )
            r.raise_for_status()
            pr = r.json()
        return PullRequest(
            number=pr["number"],
            url=pr["html_url"],
            head=head,
            base=base,
            draft=draft,
            mode="live",
        )

    def _set_draft(self, node_id: str, draft: bool) -> None:
        mutation = "convertPullRequestToDraft" if draft else "markPullRequestReadyForReview"
        query = f"mutation($id: ID!) {{ {mutation}(input: {{pullRequestId: $id}}) {{ pullRequest {{ isDraft }} }} }}"
        r = self.http.post("/graphql", json={"query": query, "variables": {"id": node_id}})
        r.raise_for_status()
        if r.json().get("errors"):
            raise RuntimeError(f"GitHub {mutation} failed: {r.json()['errors']}")

    def comment(self, repo: str, number: int, body: str) -> None:
        self.http.post(f"/repos/{repo}/issues/{number}/comments", json={"body": body}).raise_for_status()

    def merged(self, repo: str, number: int) -> bool | None:
        r = self.http.get(f"/repos/{repo}/pulls/{number}")
        return bool(r.json().get("merged")) if r.status_code == 200 else None


class GitHubMock:
    def __init__(self, root: Path = ROOT / ".data" / "mock" / "github") -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def remote_branch_exists(self, repo: str, branch: str) -> bool:
        return True

    def push(self, worktree: Path, branch: str) -> None:
        patch = Workspace(worktree).git("format-patch", "-1", "--stdout", check=True).stdout
        (self.root / f"{branch.replace('/', '__')}.patch").write_text(patch)

    def open_pr(self, repo: str, head: str, base: str, title: str, body: str, draft: bool) -> PullRequest:
        n = len(list(self.root.glob("pr-*.json"))) + 1
        (self.root / f"pr-{n}.json").write_text(
            json.dumps(
                {
                    "number": n,
                    "repo": repo,
                    "head": head,
                    "base": base,
                    "title": title,
                    "body": body,
                    "draft": draft,
                    "created": datetime.now(UTC).isoformat(),
                },
                indent=2,
            )
        )
        return PullRequest(
            number=n, url=f"mock://github/{repo}/pull/{n}", head=head, base=base, draft=draft, mode="mock"
        )

    def comment(self, repo: str, number: int, body: str) -> None:
        with (self.root / f"pr-{number}-comments.md").open("a") as f:
            f.write(body + "\n\n---\n")

    def merged(self, repo: str, number: int) -> bool | None:
        return None  # unknown: a local deploy of the bot branch stands in for the merge
