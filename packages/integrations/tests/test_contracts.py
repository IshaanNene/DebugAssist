"""Contract tests (ROADMAP-100 025): our clients against API responses recorded live by
`scripts/record_contracts.py` (fixtures/contracts/; read-only calls, redacted). Offline they replay the recordings
through httpx.MockTransport; with DA_LIVE_TESTS=1 the `live` tests fetch the same endpoints again and check that
every field our clients read is still there. Workers AI (Clef) has its own recordings under
packages/decisions/tests/fixtures/workers_ai/.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from debugassist.core import openrouter
from debugassist.integrations.github import GitHubLive
from debugassist.integrations.jira import JiraCloud

FIX = Path(__file__).parent / "fixtures" / "contracts"
ROOT = Path(__file__).resolve().parents[3]
REPO = "IshaanNene/miniride-client"


def _rec(service: str) -> dict[str, Any]:
    return json.loads((FIX / f"{service}.json").read_text())


def _replay(calls: dict[str, dict[str, Any]], seen: list[httpx.Request]) -> httpx.MockTransport:
    """Answer each request with the recording whose method and path match (query strings aside)."""

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        for c in calls.values():
            if c["request"]["method"] == req.method and c["request"]["path"] == req.url.path:
                return httpx.Response(c["status"], json=c["body"])
        if req.method == "PATCH" and req.url.path.startswith(f"/repos/{REPO}/pulls/"):
            return httpx.Response(200, json=calls["pull"]["body"])  # our update: GitHub echoes the PR
        return httpx.Response(404, json={"message": "not recorded"})

    return httpx.MockTransport(handler)


def _github(seen: list[httpx.Request]) -> GitHubLive:
    gh = GitHubLive("token-not-used")
    gh.http = httpx.Client(base_url="https://api.github.com", transport=_replay(_rec("github"), seen))
    return gh


# ---- GitHub ----------------------------------------------------------------------------------


def test_github_branch_lookup_reads_the_status_only() -> None:
    gh = _github([])
    assert gh.remote_branch_exists(REPO, "main") is True
    assert gh.remote_branch_exists(REPO, "debugassist/no-such-branch") is False


def test_github_merged_reads_the_pull_requests_merged_flag() -> None:
    pull = _rec("github")["pull"]["body"]
    assert _github([]).merged(REPO, pull["number"]) is bool(pull["merged"])


def test_github_open_pr_updates_an_existing_pr_from_the_recorded_list() -> None:
    rec = _rec("github")
    listed = rec["pulls"]["body"][0]
    seen: list[httpx.Request] = []
    pr = _github(seen).open_pr(
        REPO, listed["head"]["ref"], listed["base"]["ref"], "fix: title", "body", draft=bool(listed["draft"])
    )
    assert (pr.number, pr.url, pr.mode) == (listed["number"], listed["html_url"], "live")
    assert [r.method for r in seen] == ["GET", "PATCH"]  # found it, updated it; no GraphQL (draft unchanged)
    assert json.loads(seen[1].content) == {"title": "fix: title", "body": "body"}


def test_github_recordings_carry_the_fields_the_client_reads() -> None:
    rec = _rec("github")
    for f in ("number", "html_url", "node_id", "draft", "merged"):
        assert f in rec["pull"]["body"], f
    assert {"number", "html_url", "node_id", "draft"} <= set(rec["pulls"]["body"][0])


# ---- Jira ------------------------------------------------------------------------------------


def test_jira_search_request_matches_the_recording_and_an_empty_result_is_no_ticket() -> None:
    rec = _rec("jira")
    seen: list[httpx.Request] = []
    j = JiraCloud("https://example.atlassian.net", "user@example.test", "token-not-used", "SCRUM",
                  http=httpx.Client(transport=_replay(rec, seen)))  # fmt: skip
    assert j.find_open("debugassist") is None  # the recorded search has no issues
    sent = json.loads(seen[0].content)
    assert seen[0].url.path == rec["search"]["request"]["path"] == "/rest/api/3/search/jql"
    assert set(sent) == set(rec["search"]["request"]["json"])  # same request shape as the live call
    assert "issues" in rec["search"]["body"]


# ---- OpenRouter ------------------------------------------------------------------------------


def test_openrouter_catalog_entry_gives_capabilities_and_prices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    [entry] = _rec("openrouter")["models"]["body"]["data"]
    cache = tmp_path / "models.json"
    cache.write_text(json.dumps([entry]))
    monkeypatch.setattr(openrouter, "CACHE", cache)
    openrouter.model_info.cache_clear()
    try:
        info = openrouter.model_info(entry["id"])
    finally:
        openrouter.model_info.cache_clear()
    assert info.id == entry["id"] and info.context_length == int(entry["context_length"])
    assert info.price_in_per_mtok == pytest.approx(float(entry["pricing"]["prompt"]) * 1e6)
    assert info.price_out_per_mtok == pytest.approx(float(entry["pricing"]["completion"]) * 1e6)
    assert info.supported_parameters == entry["supported_parameters"] and "tools" in info.supported_parameters


# ---- live: the same calls today --------------------------------------------------------------


def _recorder() -> Any:
    spec = importlib.util.spec_from_file_location(
        "record_contracts", ROOT / "scripts" / "record_contracts.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.live
def test_live_github_still_has_the_fields_we_read() -> None:
    now = _recorder().github()
    assert now["branch"]["status"] == 200 and now["branch_missing"]["status"] == 404
    assert {"number", "html_url", "node_id", "draft", "merged"} <= set(now["pull"]["body"])


@pytest.mark.live
def test_live_jira_search_still_answers_with_issues() -> None:
    assert "issues" in _recorder().jira()["search"]["body"]


@pytest.mark.live
def test_live_openrouter_entry_still_has_pricing_and_parameters() -> None:
    [entry] = _recorder().openrouter()["models"]["body"]["data"]
    assert {"prompt", "completion"} <= set(entry["pricing"]) and entry["supported_parameters"]
