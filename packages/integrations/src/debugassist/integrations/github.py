"""GitHub: push bot branches and open pull requests (REST), or record them locally in mock mode."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import httpx
from pydantic import BaseModel

from debugassist.core.policy import ROOT


class PullRequest(BaseModel):
    number: int
    url: str
    head: str
    base: str
    draft: bool
    mode: str


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
        )

    def remote_branch_exists(self, repo: str, branch: str) -> bool:
        return self.http.get(f"/repos/{repo}/branches/{branch}").status_code == 200

    def push(self, worktree: Path, branch: str) -> None:
        # Uses the developer's configured git remote credentials (the token never enters the sandbox).
        subprocess.run(
            ["git", "push", "-q", "-f", "origin", f"HEAD:refs/heads/{branch}"], cwd=worktree, check=True
        )

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
        patch = subprocess.run(
            ["git", "format-patch", "-1", "--stdout"],
            cwd=worktree,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
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
