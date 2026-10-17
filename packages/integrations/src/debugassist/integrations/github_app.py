"""GitHub App: read issues on the repositories it is installed on, and act there as the app (live or mock).

The app authenticates with a short-lived JWT signed by its private key, exchanges it for an installation access
token per installation (valid an hour, cached until a few minutes before it expires), and uses that token for
REST calls and for `git` over HTTPS. The private key is read from a file named in the environment; it and the
tokens never enter a sandbox.

Which repositories the app may write to is the write policy's call (`configs/policies/writes.yaml`,
`app_installations`): with it on, an installed repository counts as allowed, still for `debugassist/*` branches
and draft pull requests only.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, cast

import httpx
import jwt

from debugassist.core import hostgit
from debugassist.core.policy import ROOT
from debugassist.integrations.github import GitHubLive, check_rate_limit

API = "https://api.github.com"
MAX_PAGES = 50
REPOS_TTL = 600.0  # seconds
MARKER = "<!-- debugassist:"  # starts every comment the app writes, so a poll never runs an issue twice


@dataclass(frozen=True)
class AppIssue:
    repo: str  # owner/name
    number: int
    title: str
    body: str
    url: str
    created_at: str
    labels: tuple[str, ...]


@dataclass(frozen=True)
class CheckRun:
    """A finished CI check (a check run), the input for a CI failure (ROADMAP-100 074)."""

    repo: str
    id: int
    name: str
    conclusion: str
    head_sha: str
    url: str
    title: str
    summary: str
    text: str
    completed_at: str


def _check_run(repo: str, d: dict[str, Any]) -> CheckRun:
    out = cast(dict[str, Any], d.get("output") or {})
    return CheckRun(
        repo=repo,
        id=int(d["id"]),
        name=str(d.get("name") or "check"),
        conclusion=str(d.get("conclusion") or ""),
        head_sha=str(d.get("head_sha") or ""),
        url=str(d.get("html_url") or ""),
        title=str(out.get("title") or ""),
        summary=str(out.get("summary") or ""),
        text=str(out.get("text") or ""),
        completed_at=str(d.get("completed_at") or ""),
    )


class GitHubApp(Protocol):
    def installed_repos(self) -> list[str]: ...
    def labeled_issues(self, repo: str, label: str) -> list[AppIssue]: ...
    def issue(self, repo: str, number: int) -> AppIssue: ...
    def check_run(self, repo: str, check_id: int) -> CheckRun: ...
    def comments(self, repo: str, number: int) -> list[str]: ...
    def repo_info(self, repo: str) -> dict[str, Any]: ...
    def clone_url(self, repo: str) -> str: ...
    def git_env(self, repo: str) -> dict[str, str]: ...
    def client(self, repo: str) -> GitHubLive | None: ...
    def comment(self, repo: str, number: int, body: str) -> None: ...


def git_auth_env(token: str) -> dict[str, str]:
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
        "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}",
        "GIT_TERMINAL_PROMPT": "0",
    }


def app_jwt(app_id: str, private_key: str, now: int | None = None) -> str:
    """The app's own token (RS256, 9 minutes, issued a minute in the past for clock drift)."""
    t = int(now if now is not None else time.time())
    return jwt.encode({"iat": t - 60, "exp": t + 540, "iss": app_id}, private_key, algorithm="RS256")


def verify_signature(secret: str, body: bytes, signature: str | None) -> bool:
    """A webhook delivery's `X-Hub-Signature-256` header, checked in constant time."""
    if not signature or not signature.startswith("sha256="):
        return False
    want = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(want, signature)


def _issue(repo: str, d: dict[str, Any]) -> AppIssue:
    return AppIssue(
        repo=repo,
        number=int(d["number"]),
        title=str(d.get("title") or ""),
        body=str(d.get("body") or ""),
        url=str(d.get("html_url") or ""),
        created_at=str(d.get("created_at") or ""),
        labels=tuple(str(lbl["name"]) for lbl in cast(list[dict[str, Any]], d.get("labels") or [])),
    )


class GitHubAppLive:
    def __init__(self, app_id: str, private_key: str, http: httpx.Client | None = None) -> None:
        self.app_id = app_id
        self.key = private_key
        self.http = http or httpx.Client(base_url=API, timeout=30)
        self.http.event_hooks["response"] = [*self.http.event_hooks["response"], check_rate_limit]
        self._tokens: dict[int, tuple[str, float]] = {}  # installation id → (token, expires at)
        self._repos: dict[str, int] | None = None  # owner/name → installation id
        self._repos_at = 0.0  # refreshed every REPOS_TTL: installs and uninstalls show up without a restart

    def _headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"}  # fmt: skip

    def _installation_token(self, installation: int) -> str:
        cached = self._tokens.get(installation)
        if cached and cached[1] - time.time() > 300:
            return cached[0]
        r = self.http.post(
            f"/app/installations/{installation}/access_tokens",
            headers=self._headers(app_jwt(self.app_id, self.key)),
        )
        r.raise_for_status()
        d = r.json()
        expires = datetime.fromisoformat(str(d["expires_at"]).replace("Z", "+00:00")).timestamp()
        self._tokens[installation] = (str(d["token"]), expires)
        return str(d["token"])

    def _map(self) -> dict[str, int]:
        if self._repos is None or time.time() - self._repos_at > REPOS_TTL:
            repos: dict[str, int] = {}
            r = self.http.get("/app/installations", headers=self._headers(app_jwt(self.app_id, self.key)))
            r.raise_for_status()
            for inst in cast(list[dict[str, Any]], r.json()):
                token = self._installation_token(int(inst["id"]))
                page = 1
                while True:
                    rr = self.http.get(
                        "/installation/repositories",
                        headers=self._headers(token),
                        params={"per_page": 100, "page": page},
                    )
                    rr.raise_for_status()
                    items = cast(list[dict[str, Any]], rr.json().get("repositories") or [])
                    repos.update({str(x["full_name"]): int(inst["id"]) for x in items})
                    if len(items) < 100:
                        break
                    page += 1
            self._repos, self._repos_at = repos, time.time()
        return self._repos

    def refresh(self) -> None:
        """Forget the installation map: an `installation` webhook said it changed."""
        self._repos = None

    def _token(self, repo: str) -> str:
        if repo not in self._map():
            raise PermissionError(f"the app is not installed on {repo}")
        return self._installation_token(self._map()[repo])

    def _get(self, repo: str, path: str, **params: Any) -> Any:
        r = self.http.get(path, headers=self._headers(self._token(repo)), params=params or None)
        r.raise_for_status()
        return r.json()

    def _get_all(self, repo: str, path: str, **params: Any) -> list[dict[str, Any]]:
        """Every page of a list endpoint (GitHub returns 30 items by default and 100 at most per page): a
        marker comment past the first page must still be seen, or the poll runs the issue again forever."""
        out: list[dict[str, Any]] = []
        url: str | None = path
        query: dict[str, Any] | None = {**params, "per_page": 100}
        for _ in range(MAX_PAGES):
            if url is None:
                break
            r = self.http.get(url, headers=self._headers(self._token(repo)), params=query)
            r.raise_for_status()
            out += cast(list[dict[str, Any]], r.json())
            url, query = r.links.get("next", {}).get("url"), None  # the next link carries the query
        return out

    def installed_repos(self) -> list[str]:
        return sorted(self._map())

    def labeled_issues(self, repo: str, label: str) -> list[AppIssue]:
        items = self._get_all(repo, f"/repos/{repo}/issues", labels=label, state="open")
        return [_issue(repo, d) for d in items if "pull_request" not in d]  # the issues API lists PRs too

    def issue(self, repo: str, number: int) -> AppIssue:
        return _issue(repo, cast(dict[str, Any], self._get(repo, f"/repos/{repo}/issues/{number}")))

    def check_run(self, repo: str, check_id: int) -> CheckRun:
        return _check_run(repo, cast(dict[str, Any], self._get(repo, f"/repos/{repo}/check-runs/{check_id}")))

    def comments(self, repo: str, number: int) -> list[str]:
        items = self._get_all(repo, f"/repos/{repo}/issues/{number}/comments")
        return [str(c.get("body") or "") for c in items]

    def repo_info(self, repo: str) -> dict[str, Any]:
        return cast(dict[str, Any], self._get(repo, f"/repos/{repo}"))

    def clone_url(self, repo: str) -> str:
        return f"https://github.com/{repo}.git"  # no credentials: they go in git_env, never in a URL or argv

    def git_env(self, repo: str) -> dict[str, str]:
        """Environment that authenticates git to github.com as the installation, as actions/checkout does.

        A token in the URL ends up in argv, so in any CalledProcessError, run state, trace or log that
        records the failed command; the environment is not."""
        return git_auth_env(self._token(repo))

    def comment(self, repo: str, number: int, body: str) -> None:
        r = self.http.post(
            f"/repos/{repo}/issues/{number}/comments",
            headers=self._headers(self._token(repo)),
            json={"body": body},
        )
        r.raise_for_status()

    def client(self, repo: str) -> GitHubLive | None:
        return AppRepoClient(self, repo) if repo in self._map() else None


class AppRepoClient(GitHubLive):
    """The pipeline's GitHub client for one installed repository: REST as the app, pushes over HTTPS with the
    installation token (to a `debugassist/*` branch; the policy gate has already said so)."""

    def __init__(self, app: GitHubAppLive, repo: str) -> None:
        super().__init__(app._token(repo))  # pyright: ignore[reportPrivateUsage]
        self.app = app
        self.repo = repo

    def push(self, worktree: Path, branch: str) -> None:
        hostgit.run(
            worktree,
            "push",
            "-q",
            "-f",
            self.app.clone_url(self.repo),
            f"HEAD:refs/heads/{branch}",
            check=True,
            extra_env=self.app.git_env(self.repo),
        )


class GitHubAppMock:
    """Mock mode: installations, issues and comments in `.data/mock/github-app/state.json`; comments the
    pipeline writes are appended there, so a poll sees its own marker as the live app would."""

    def __init__(self, root: Path = ROOT / ".data" / "mock" / "github-app") -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.state_file = root / "state.json"

    def _state(self) -> dict[str, Any]:
        if self.state_file.is_file():
            return cast(dict[str, Any], json.loads(self.state_file.read_text()))
        return {"repos": {}}

    def _save(self, s: dict[str, Any]) -> None:
        self.state_file.write_text(json.dumps(s, indent=2))

    def _repo(self, repo: str) -> dict[str, Any]:
        r = cast(dict[str, Any], self._state()["repos"]).get(repo)
        if r is None:
            raise PermissionError(f"the app is not installed on {repo}")
        return cast(dict[str, Any], r)

    def installed_repos(self) -> list[str]:
        return sorted(cast(dict[str, Any], self._state()["repos"]))

    def labeled_issues(self, repo: str, label: str) -> list[AppIssue]:
        issues = cast(list[dict[str, Any]], self._repo(repo).get("issues") or [])
        return [
            i for d in issues if d.get("state", "open") == "open" and label in (i := _issue(repo, d)).labels
        ]

    def issue(self, repo: str, number: int) -> AppIssue:
        for d in cast(list[dict[str, Any]], self._repo(repo).get("issues") or []):
            if int(d["number"]) == number:
                return _issue(repo, d)
        raise KeyError(f"{repo}#{number}")

    def check_run(self, repo: str, check_id: int) -> CheckRun:
        runs = cast(dict[str, dict[str, Any]], self._repo(repo).get("check_runs") or {})
        if str(check_id) not in runs:
            raise KeyError(f"{repo} check run {check_id}")
        return _check_run(repo, {"id": check_id, **runs[str(check_id)]})

    def comments(self, repo: str, number: int) -> list[str]:
        return [
            str(c)
            for c in cast(dict[str, list[str]], self._repo(repo).get("comments") or {}).get(str(number), [])
        ]

    def comment(self, repo: str, number: int, body: str) -> None:
        s = self._state()
        r = cast(dict[str, Any], s["repos"][repo])
        cast(dict[str, list[str]], r.setdefault("comments", {})).setdefault(str(number), []).append(body)
        self._save(s)

    def repo_info(self, repo: str) -> dict[str, Any]:
        r = self._repo(repo)
        return {
            "full_name": repo,
            "description": r.get("description", ""),
            "default_branch": r.get("default_branch", "main"),
        }

    def clone_url(self, repo: str) -> str:
        return str(self._repo(repo)["clone_url"])  # a local path in mock mode

    def git_env(self, repo: str) -> dict[str, str]:
        return {}

    def client(self, repo: str) -> GitHubLive | None:
        return None  # the pipeline's own GitHubMock records PRs and pushes


def comment_has_marker(comments: list[str]) -> bool:
    return any(c.lstrip().startswith(MARKER) for c in comments)
