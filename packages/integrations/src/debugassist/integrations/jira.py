"""Jira Cloud (REST v3) and a local mock with the same interface."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from debugassist.core.policy import ROOT

PRIORITY = {"P0": "Highest", "P1": "High", "P2": "Medium", "P3": "Low", "P4": "Lowest"}


class Ticket(BaseModel):
    key: str
    url: str
    mode: str  # live | mock


def adf(blocks: list[tuple[str, str]]) -> dict[str, Any]:
    """Atlassian Document Format from (kind, text) blocks; kind = heading | para | code | bullet."""
    content: list[dict[str, Any]] = []
    for kind, text in blocks:
        if kind == "heading":
            content.append(
                {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": text}]}
            )
        elif kind == "code":
            content.append({"type": "codeBlock", "content": [{"type": "text", "text": text}]})
        elif kind == "bullet":
            items = [ln for ln in text.splitlines() if ln.strip()]
            content.append(
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [{"type": "paragraph", "content": [{"type": "text", "text": i}]}],
                        }
                        for i in items
                    ],
                }
            )
        else:
            content.append({"type": "paragraph", "content": [{"type": "text", "text": text}]})
    return {"type": "doc", "version": 1, "content": content}


class Jira(Protocol):
    def find_open(self, label: str) -> Ticket | None: ...
    def create(
        self, summary: str, blocks: list[tuple[str, str]], priority: str, labels: list[str]
    ) -> Ticket: ...
    def comment(self, key: str, blocks: list[tuple[str, str]]) -> None: ...
    def transition(self, key: str, status: str) -> None: ...
    def link(self, key: str, url: str, title: str) -> None: ...
    def snapshot(self, key: str) -> dict[str, Any]: ...


def _adf_text(node: dict[str, Any]) -> str:
    """Plain text of an Atlassian Document Format node."""
    if node.get("type") == "text":
        return str(node.get("text", ""))
    sep = "\n" if node.get("type") in ("paragraph", "heading", "codeBlock", "listItem") else ""
    children: list[dict[str, Any]] = node.get("content", [])
    return "".join(_adf_text(c) for c in children) + sep


class JiraCloud:
    def __init__(self, base_url: str, email: str, token: str, project: str, issue_type: str = "Task") -> None:
        self.base = base_url.rstrip("/")
        self.project = project
        self.issue_type = issue_type
        self.http = httpx.Client(auth=(email, token), timeout=20, headers={"Accept": "application/json"})

    def find_open(self, label: str) -> Ticket | None:
        jql = f'project = "{self.project}" AND labels = "{label}" AND statusCategory != Done ORDER BY created DESC'
        r = self.http.post(
            f"{self.base}/rest/api/3/search/jql", json={"jql": jql, "maxResults": 1, "fields": ["key"]}
        )
        if r.status_code != 200 or not r.json().get("issues"):
            return None
        key = r.json()["issues"][0]["key"]
        return Ticket(key=key, url=f"{self.base}/browse/{key}", mode="live")

    def create(self, summary: str, blocks: list[tuple[str, str]], priority: str, labels: list[str]) -> Ticket:
        fields: dict[str, Any] = {
            "project": {"key": self.project},
            "issuetype": {"name": self.issue_type},
            "summary": summary[:250],
            "description": adf(blocks),
            "labels": labels,
            "priority": {"name": PRIORITY.get(priority, "Medium")},
        }
        r = self.http.post(f"{self.base}/rest/api/3/issue", json={"fields": fields})
        if r.status_code == 400 and "priority" in r.text:  # project without the priority field
            fields.pop("priority")
            r = self.http.post(f"{self.base}/rest/api/3/issue", json={"fields": fields})
        r.raise_for_status()
        key = r.json()["key"]
        return Ticket(key=key, url=f"{self.base}/browse/{key}", mode="live")

    def comment(self, key: str, blocks: list[tuple[str, str]]) -> None:
        self.http.post(
            f"{self.base}/rest/api/3/issue/{key}/comment", json={"body": adf(blocks)}
        ).raise_for_status()

    def transition(self, key: str, status: str) -> None:
        r = self.http.get(f"{self.base}/rest/api/3/issue/{key}/transitions").raise_for_status()
        match = next((t for t in r.json()["transitions"] if t["to"]["name"].lower() == status.lower()), None)
        if match:
            self.http.post(
                f"{self.base}/rest/api/3/issue/{key}/transitions", json={"transition": {"id": match["id"]}}
            ).raise_for_status()

    def link(self, key: str, url: str, title: str) -> None:
        existing = self.http.get(f"{self.base}/rest/api/3/issue/{key}/remotelink")
        if existing.status_code == 200 and any(li["object"]["url"] == url for li in existing.json()):
            return  # re-runs update the same PR; one link is enough
        self.http.post(
            f"{self.base}/rest/api/3/issue/{key}/remotelink", json={"object": {"url": url, "title": title}}
        ).raise_for_status()

    def snapshot(self, key: str) -> dict[str, Any]:
        """The ticket as Jira holds it now (for run reports): status, comments, remote links."""
        f = (
            self.http.get(
                f"{self.base}/rest/api/3/issue/{key}",
                params={"fields": "summary,status,priority,labels,assignee,created,updated,comment"},
            )
            .raise_for_status()
            .json()["fields"]
        )
        priority: dict[str, Any] = f.get("priority") or {}
        links = self.http.get(f"{self.base}/rest/api/3/issue/{key}/remotelink").raise_for_status().json()
        return {
            "key": key,
            "url": f"{self.base}/browse/{key}",
            "summary": f["summary"],
            "status": f["status"]["name"],
            "priority": priority.get("name"),
            "labels": f.get("labels", []),
            "created": f["created"],
            "updated": f["updated"],
            "comments": [
                {
                    "author": c["author"]["displayName"],
                    "created": c["created"],
                    "text": _adf_text(c["body"]).strip(),
                }
                for c in f["comment"]["comments"]
            ],
            "links": [{"url": li["object"]["url"], "title": li["object"]["title"]} for li in links],
            "mode": "live",
        }


class JiraMock:
    """Writes tickets as JSON files under .data/mock/jira/ (rendered by the dashboard later)."""

    def __init__(self, root: Path = ROOT / ".data" / "mock" / "jira") -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def find_open(self, label: str) -> Ticket | None:
        for f in sorted(self.root.glob("MOCK-*.json")):
            d = json.loads(f.read_text())
            if label in d["labels"] and d["status"] != "Done":
                return Ticket(key=d["key"], url=f"mock://jira/{d['key']}", mode="mock")
        return None

    def create(self, summary: str, blocks: list[tuple[str, str]], priority: str, labels: list[str]) -> Ticket:
        n = len(list(self.root.glob("MOCK-*.json"))) + 1
        key = f"MOCK-{n}"
        self._path(key).write_text(
            json.dumps(
                {
                    "key": key,
                    "summary": summary,
                    "priority": priority,
                    "labels": labels,
                    "status": "To Do",
                    "description": blocks,
                    "comments": [],
                    "links": [],
                    "created": datetime.now(UTC).isoformat(),
                },
                indent=2,
            )
        )
        return Ticket(key=key, url=f"mock://jira/{key}", mode="mock")

    def _update(self, key: str, fn: Callable[[dict[str, Any]], object]) -> None:
        data = json.loads(self._path(key).read_text())
        fn(data)
        self._path(key).write_text(json.dumps(data, indent=2))

    def comment(self, key: str, blocks: list[tuple[str, str]]) -> None:
        self._update(key, lambda d: d["comments"].append(blocks))

    def transition(self, key: str, status: str) -> None:
        self._update(key, lambda d: d.update(status=status))

    def link(self, key: str, url: str, title: str) -> None:
        self._update(key, lambda d: d["links"].append({"url": url, "title": title}))

    def snapshot(self, key: str) -> dict[str, Any]:
        d = json.loads(self._path(key).read_text())
        comments = [
            {"author": "DebugAssist", "created": "", "text": "\n".join(t for _, t in c)}
            for c in d["comments"]
        ]
        return {**d, "url": f"mock://jira/{key}", "comments": comments, "mode": "mock"}
