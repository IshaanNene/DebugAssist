"""GitHub App: the app JWT, webhook signatures, installation tokens and repositories (against a fake API), and
the policy's installation allowance."""

from __future__ import annotations

import hashlib
import hmac
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from debugassist.core.policy import Policy, PolicyGate, Verdict
from debugassist.integrations.github_app import GitHubAppLive, app_jwt, comment_has_marker, verify_signature


def _key() -> tuple[str, Any]:
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = k.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    return pem, k.public_key()


def test_app_jwt_is_rs256_signed_with_the_app_id_and_a_short_life() -> None:
    pem, pub = _key()
    claims = jwt.decode(
        app_jwt("12345", pem, now=1_800_000_000),
        pub,
        algorithms=["RS256"],
        options={"verify_exp": False, "verify_iat": False},
    )
    assert claims == {"iat": 1_800_000_000 - 60, "exp": 1_800_000_000 + 540, "iss": "12345"}


def test_webhook_signature_is_checked() -> None:
    body = b'{"action":"labeled"}'
    good = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    assert verify_signature("s3cret", body, good)
    assert not verify_signature("s3cret", body + b" ", good)
    assert not verify_signature("other", body, good)
    assert not verify_signature("s3cret", body, None) and not verify_signature("s3cret", body, "sha1=abc")


def _fake_api(calls: list[str]) -> httpx.Client:
    expires = (datetime.now(UTC) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(f"{req.method} {req.url.path}")
        p = req.url.path
        if p == "/app/installations":
            assert req.headers["authorization"].startswith("Bearer ey")  # the app JWT
            return httpx.Response(200, json=[{"id": 7}])
        if p == "/app/installations/7/access_tokens":
            return httpx.Response(201, json={"token": "ghs_inst", "expires_at": expires})
        assert req.headers["authorization"] == "Bearer ghs_inst"  # everything else as the installation
        if p == "/installation/repositories":
            return httpx.Response(200, json={"repositories": [{"full_name": "acme/widgets"}]})
        if p == "/repos/acme/widgets/issues":
            assert req.url.params["labels"] == "debugassist"
            return httpx.Response(200, json=[
                {"number": 3, "title": "Crash", "body": "boom", "html_url": "u3", "created_at": "t", "labels": [{"name": "debugassist"}]},
                {"number": 4, "title": "A PR", "pull_request": {}, "labels": [{"name": "debugassist"}]},
            ])  # fmt: skip
        if p == "/repos/acme/widgets/issues/3/comments" and req.method == "GET":
            return httpx.Response(200, json=[{"body": "<!-- debugassist:run x -->\nDone"}])
        if p == "/repos/acme/widgets/issues/3/comments" and req.method == "POST":
            assert json.loads(req.content)["body"] == "hello"
            return httpx.Response(201, json={})
        return httpx.Response(404, json={})

    return httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler))


def test_installation_tokens_repositories_and_issues() -> None:
    pem, _ = _key()
    calls: list[str] = []
    a = GitHubAppLive("12345", pem, http=_fake_api(calls))
    assert a.installed_repos() == ["acme/widgets"]
    [issue] = a.labeled_issues("acme/widgets", "debugassist")  # the PR is dropped
    assert (issue.number, issue.title, issue.labels) == (3, "Crash", ("debugassist",))
    assert comment_has_marker(a.comments("acme/widgets", 3))
    a.comment("acme/widgets", 3, "hello")
    assert a.clone_url("acme/widgets") == "https://github.com/acme/widgets.git"  # no token in URLs
    assert "ghs_inst" not in json.dumps(
        a.git_env("acme/widgets")
    )  # base64 in an extraheader, as checkout does
    assert calls.count("POST /app/installations/7/access_tokens") == 1  # cached
    try:
        a.issue("acme/other", 1)
        raise AssertionError("expected PermissionError")
    except PermissionError:
        pass


def test_the_policy_allows_installed_repos_only_when_it_says_so() -> None:
    base = {
        "actions": {"github.comment": "live"},
        "repos": ["me/listed"],
        "branches": {"push_prefix": "debugassist/"},
    }
    on = PolicyGate(
        Policy.model_validate({**base, "app_installations": True}), installed=lambda: ["acme/widgets"]
    )
    off = PolicyGate(Policy.model_validate(base), installed=lambda: ["acme/widgets"])
    assert on.verdict("github.comment", repo="acme/widgets") is Verdict.LIVE
    assert on.verdict("github.comment", repo="acme/elsewhere") is Verdict.DENY
    assert off.verdict("github.comment", repo="acme/widgets") is Verdict.DENY
    assert (
        on.verdict("github.push_branch", repo="acme/widgets", branch="main") is Verdict.DENY
    )  # bot branches only

    def down() -> list[str]:
        raise httpx.ConnectError("no network")

    assert not PolicyGate(
        Policy.model_validate({**base, "app_installations": True}), installed=down
    ).allowed_repo("acme/widgets")


def test_a_failed_push_never_carries_the_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Audit P1-2: the token was in the push URL, so in argv and in the CalledProcessError the graph persisted."""
    pem, _ = _key()
    a = GitHubAppLive("12345", pem, http=_fake_api([]))
    repo = tmp_path / "wt"
    repo.mkdir()
    for args in (["init", "-q"], ["commit", "-q", "--allow-empty", "-m", "x"]):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=repo, check=True)
    cfg = tmp_path / "gitconfig"  # github.com resolves to a path that does not exist: the push fails offline
    cfg.write_text(f'[url "{tmp_path}/missing/"]\n\tinsteadOf = https://github.com/\n')
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    client = a.client("acme/widgets")
    assert client is not None
    with pytest.raises(subprocess.CalledProcessError) as err:
        client.push(repo, "debugassist/fix")
    exc = err.value
    seen = " ".join([str(exc), repr(exc), str(exc.cmd), str(exc.stdout), str(exc.stderr)])
    assert "ghs_inst" not in seen
    assert "ghs_inst" not in (repo / ".git" / "config").read_text()


def test_comments_and_labeled_issues_are_read_across_pages() -> None:
    """Audit P2-12: one page of 100 comments hid a marker on page two, so the poll re-ran the issue forever."""
    pem, _ = _key()
    expires = (datetime.now(UTC) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    comments = [{"body": f"c{i}"} for i in range(149)] + [{"body": "<!-- debugassist:run x -->"}]
    issues = [{"number": i, "title": "t", "labels": [{"name": "debugassist"}]} for i in range(45)]

    def page(items: list[dict[str, Any]], req: httpx.Request) -> httpx.Response:
        n = int(req.url.params.get("page", "1"))
        size = int(req.url.params.get("per_page", "30"))
        headers: dict[str, str] = {}
        if n * size < len(items):
            nxt = req.url.copy_merge_params({"page": str(n + 1), "per_page": str(size)})
            headers["link"] = f'<{nxt}>; rel="next"'
        return httpx.Response(200, json=items[(n - 1) * size : n * size], headers=headers)

    def handler(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == "/app/installations":
            return httpx.Response(200, json=[{"id": 7}])
        if p == "/app/installations/7/access_tokens":
            return httpx.Response(201, json={"token": "ghs_inst", "expires_at": expires})
        if p == "/installation/repositories":
            return httpx.Response(200, json={"repositories": [{"full_name": "acme/widgets"}]})
        if p == "/repos/acme/widgets/issues/3/comments":
            return page(comments, req)
        if p == "/repos/acme/widgets/issues":
            return page(issues, req)
        return httpx.Response(404, json={})

    a = GitHubAppLive(
        "1", pem, http=httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler))
    )
    got = a.comments("acme/widgets", 3)
    assert len(got) == 150 and comment_has_marker(got)
    assert len(a.labeled_issues("acme/widgets", "debugassist")) == 45


def test_rate_limits_become_a_wait_not_an_error_to_retry() -> None:
    """ROADMAP-100 047: primary and secondary limits say how long to wait."""
    from debugassist.integrations.github import RateLimited, check_rate_limit

    def resp(status: int, **headers: str) -> httpx.Response:
        return httpx.Response(status, headers=headers)

    check_rate_limit(resp(200, **{"x-ratelimit-remaining": "0"}))  # a success is never an error
    check_rate_limit(resp(403))  # a plain permission error stays one
    with pytest.raises(RateLimited) as primary:
        check_rate_limit(resp(403, **{"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1060"}), now=1000)
    assert primary.value.wait_s == 60
    with pytest.raises(RateLimited) as secondary:
        check_rate_limit(resp(429, **{"retry-after": "30"}))
    assert secondary.value.wait_s == 30

    pem, _ = _key()

    def limited(req: httpx.Request) -> httpx.Response:
        return httpx.Response(403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "0"}, json={})

    a = GitHubAppLive(
        "1", pem, http=httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(limited))
    )
    with pytest.raises(RateLimited):
        a.installed_repos()
