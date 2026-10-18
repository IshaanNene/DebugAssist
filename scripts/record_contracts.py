"""Record the API responses our clients depend on, for the contract tests (ROADMAP-100 025). Read-only calls only.

    uv run --no-sync python scripts/record_contracts.py [github] [jira] [openrouter]

Writes `packages/integrations/tests/fixtures/contracts/<service>.json`: per call, the request we make and the
response's status and body. Redacted before writing: e-mail addresses, Atlassian account ids, avatar URLs,
display names, and the Jira site's host (→ example.atlassian.net). Only the OpenRouter catalog entry of the model in
use is kept. Workers AI (Clef) responses are already recorded under packages/decisions/tests/fixtures/workers_ai/.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import httpx

from debugassist.core.settings import get_settings

# applied to every recording: e-mails (commit authors on GitHub), Atlassian identities, avatars
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "packages" / "integrations" / "tests" / "fixtures" / "contracts"
REPO = "IshaanNene/miniride-client"
JIRA_FIELDS = "summary,status,priority,labels,assignee,created,updated,comment"
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def redact(v: Any, host: str | None = None) -> Any:
    if isinstance(v, dict):
        out: dict[str, Any] = {}
        for k, x in cast(dict[str, Any], v).items():
            if k in {"emailAddress", "email"}:
                out[k] = "user@example.test"
            elif k == "accountId":
                out[k] = "account-redacted"
            elif k in {"avatarUrls", "avatar_url", "gravatar_id"}:
                out[k] = {} if isinstance(x, dict) else ""
            elif k == "displayName":
                out[k] = "A User"
            else:
                out[k] = redact(x, host)
        return out
    if isinstance(v, list):
        return [redact(x, host) for x in cast(list[Any], v)]
    if isinstance(v, str):
        s = _EMAIL.sub(lambda m: m.group(0) if m.group(0) == "git@github.com" else "user@example.test", v)
        return s.replace(host, "example.atlassian.net") if host else s
    return v


def _call(http: httpx.Client, method: str, url: str, **kw: Any) -> dict[str, Any]:
    r = http.request(method, url, **kw)
    body: Any = (
        r.json() if r.headers.get("content-type", "").startswith("application/json") and r.content else None
    )
    req: dict[str, Any] = {"method": method, "path": urlparse(url).path or url}
    if kw.get("params"):
        req["params"] = kw["params"]
    if kw.get("json") is not None:
        req["json"] = kw["json"]
    return {"request": req, "status": r.status_code, "body": body}


def github() -> dict[str, Any]:
    s = get_settings()
    if s.github_token is None:
        raise SystemExit("GITHUB_TOKEN is not set")
    http = httpx.Client(
        base_url="https://api.github.com",
        timeout=30,
        headers={
            "Authorization": f"Bearer {s.github_token.get_secret_value()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    pulls = _call(http, "GET", f"/repos/{REPO}/pulls", params={"state": "all", "per_page": 1})
    number = pulls["body"][0]["number"]
    return redact(
        {
            "branch": _call(http, "GET", f"/repos/{REPO}/branches/main"),
            "branch_missing": _call(http, "GET", f"/repos/{REPO}/branches/debugassist/no-such-branch"),
            "pulls": pulls,
            "pull": _call(http, "GET", f"/repos/{REPO}/pulls/{number}"),
        }
    )


def jira() -> dict[str, Any]:
    s = get_settings()
    if None in (s.jira_base_url, s.jira_email, s.jira_api_key):
        raise SystemExit("JIRA_BASE_URL, JIRA_EMAIL and JIRA_API_KEY are needed")
    assert s.jira_base_url and s.jira_email and s.jira_api_key
    base = s.jira_base_url.rstrip("/")
    http = httpx.Client(auth=(s.jira_email, s.jira_api_key.get_secret_value()), timeout=20,
                        headers={"Accept": "application/json"})  # fmt: skip
    project = "SCRUM"
    search = _call(http, "POST", f"{base}/rest/api/3/search/jql",
                   json={"jql": f'project = "{project}" ORDER BY created DESC', "maxResults": 1, "fields": ["key"]})  # fmt: skip
    issues = cast(list[dict[str, Any]], cast(dict[str, Any], search["body"] or {}).get("issues") or [])
    out: dict[str, Any] = {"search": search}
    if not issues:  # nothing visible to this token: the empty search is still a contract (find_open → None)
        print(f"jira: no issues visible in {project}; recorded the search only")
    else:
        key = issues[0]["key"]
        out |= {
            "issue": _call(http, "GET", f"{base}/rest/api/3/issue/{key}", params={"fields": JIRA_FIELDS}),
            "remotelinks": _call(http, "GET", f"{base}/rest/api/3/issue/{key}/remotelink"),
            "transitions": _call(http, "GET", f"{base}/rest/api/3/issue/{key}/transitions"),
        }
    return redact(out, urlparse(base).netloc)


def openrouter() -> dict[str, Any]:
    model = get_settings().model()
    r = _call(httpx.Client(timeout=30), "GET", "https://openrouter.ai/api/v1/models")
    data = [m for m in r["body"]["data"] if m["id"] == model]
    if not data:
        raise SystemExit(f"{model} is not in OpenRouter's catalog")
    return redact({"models": {**r, "body": {"data": data}}})


def main(args: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in args or ["github", "jira", "openrouter"]:
        data = {"github": github, "jira": jira, "openrouter": openrouter}[name]()
        text = json.dumps(data, indent=2, sort_keys=True) + "\n"
        (OUT / f"{name}.json").write_text(text)
        print(f"{name}: {len(data)} calls, {len(text)} bytes → {(OUT / f'{name}.json').relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])
