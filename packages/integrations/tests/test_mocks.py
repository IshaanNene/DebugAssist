from __future__ import annotations

import subprocess
from pathlib import Path

from debugassist.integrations.github import GitHubMock
from debugassist.integrations.jira import JiraMock, _adf_text, adf  # pyright: ignore[reportPrivateUsage]


def test_jira_mock_lifecycle(tmp_path: Path) -> None:
    j = JiraMock(tmp_path)
    t = j.create("crash", [("para", "root cause")], "P2", ["debugassist", "vitals-vit-1"])
    assert t.mode == "mock" and j.find_open("vitals-vit-1") == t
    j.comment(t.key, [("para", "fix ready")])
    j.link(t.key, "mock://github/x/pull/1", "PR #1")
    j.transition(t.key, "In Review")
    snap = j.snapshot(t.key)
    assert snap["status"] == "In Review" and snap["mode"] == "mock"
    assert snap["comments"][0]["text"] == "fix ready" and snap["links"][0]["title"] == "PR #1"
    j.transition(t.key, "Done")
    assert j.find_open("vitals-vit-1") is None


def test_adf_round_trip() -> None:
    doc = adf([("heading", "Root cause"), ("para", "routeV2 reads the session too early")])
    text = _adf_text(doc)
    assert "Root cause" in text and "routeV2 reads the session too early" in text


def test_github_mock_writes_patch_and_pr(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "a.txt").write_text("a\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run([*git, "commit", "-qm", "fix: a"], cwd=repo, check=True)
    gh = GitHubMock(tmp_path / "gh")
    gh.push(repo, "debugassist/vit-1")
    pr = gh.open_pr("o/r", "debugassist/vit-1", "release/1.6.1", "fix: a", "body", draft=True)
    assert pr.mode == "mock" and pr.draft and pr.url == "mock://github/o/r/pull/1"
    assert "fix: a" in (tmp_path / "gh" / "debugassist__vit-1.patch").read_text()


def test_jira_retries_busy_responses_and_never_posts_a_comment_twice() -> None:
    """ROADMAP-100 079."""
    import json

    import httpx

    from debugassist.integrations.jira import JiraCloud, adf

    comments: list[dict[str, object]] = []
    posts = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/comment") and req.method == "GET":
            return httpx.Response(200, json={"comments": [{"body": c} for c in comments]})
        if req.url.path.endswith("/comment") and req.method == "POST":
            posts["n"] += 1
            if posts["n"] == 1:
                return httpx.Response(503, headers={"retry-after": "1"})
            comments.append(json.loads(req.content)["body"])
            return httpx.Response(201, json={})
        return httpx.Response(404)

    waits: list[float] = []
    j = JiraCloud(
        "https://x.atlassian.net",
        "e",
        "t",
        "SCRUM",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=waits.append,
    )
    j.comment("SCRUM-1", [("para", "Root cause: off by one")])
    j.comment("SCRUM-1", [("para", "Root cause: off by one")])  # a resumed run says the same thing
    j.comment("SCRUM-1", [("para", "Fixed in PR #3")])
    assert waits == [1.0] and posts["n"] == 3 and len(comments) == 2
    assert comments[0] == adf([("para", "Root cause: off by one")])
