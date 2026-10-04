import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from debugassist.decisions.backends.workers_ai import WorkersAIClef
from debugassist.decisions.resilience import RetryPolicy
from debugassist.decisions.schema import ClefRequest, ClefRequestError, ClefResponseError, ClefTransientError

FAST = RetryPolicy(max_attempts=3, base_delay_s=0.0, max_delay_s=0.0)


def backend(handler: Any) -> WorkersAIClef:
    return WorkersAIClef("acct123", "tok", transport=httpx.MockTransport(handler), retry=FAST)


@pytest.fixture
def request_(basic_questions: dict[str, Any]) -> ClefRequest:
    return ClefRequest.model_validate(
        {"model": "clef", "state": {"error": "boom"}, "questions": basic_questions}
    )


async def test_happy_path_sends_contract_and_unwraps(
    request_: ClefRequest, clef_fixture: dict[str, Any]
) -> None:
    seen: dict[str, Any] = {}

    def handler(r: httpx.Request) -> httpx.Response:
        seen["url"] = str(r.url)
        seen["auth"] = r.headers["authorization"]
        seen["body"] = json.loads(r.content)
        return httpx.Response(200, json=clef_fixture)

    b = backend(handler)
    resp = await b.run(request_)
    assert seen["url"] == "https://api.cloudflare.com/client/v4/accounts/acct123/ai/run/@cf/cloudflare/clef"
    assert seen["auth"] == "Bearer tok"
    assert seen["body"]["model"] == "clef" and set(seen["body"]["questions"]) == set(request_.questions)
    assert resp.answers["category"].type == "choice"
    assert b.cost_usd(resp) == pytest.approx(402 * 0.24 / 1e6)
    await b.aclose()


async def test_flash_path_and_price(basic_questions: dict[str, Any]) -> None:
    payload = json.loads((Path(__file__).parent / "fixtures/workers_ai/clef-flash_basic.json").read_text())
    urls: list[str] = []

    def handler(r: httpx.Request) -> httpx.Response:
        urls.append(str(r.url))
        return httpx.Response(200, json=payload)

    b = backend(handler)
    req = ClefRequest.model_validate({"model": "clef-flash", "state": "s", "questions": basic_questions})
    resp = await b.run(req)
    assert urls[0].endswith("@cf/cloudflare/clef-flash")
    assert b.cost_usd(resp) == pytest.approx(402 * 0.09 / 1e6)


async def test_retries_transient_then_succeeds(request_: ClefRequest, clef_fixture: dict[str, Any]) -> None:
    calls = {"n": 0}

    def handler(r: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, text="slow down")
        if calls["n"] == 2:
            return httpx.Response(503, text="unavailable")
        return httpx.Response(200, json=clef_fixture)

    await backend(handler).run(request_)
    assert calls["n"] == 3


async def test_gives_up_after_max_attempts(request_: ClefRequest) -> None:
    calls = {"n": 0}

    def handler(r: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ReadTimeout("timeout")

    with pytest.raises(ClefTransientError):
        await backend(handler).run(request_)
    assert calls["n"] == 3


async def test_client_errors_are_not_retried(request_: ClefRequest) -> None:
    calls = {"n": 0}

    def handler(r: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={"success": False, "errors": [{"message": "bad questions"}]})

    with pytest.raises(ClefRequestError, match="400"):
        await backend(handler).run(request_)
    assert calls["n"] == 1


async def test_mismatched_answers_rejected(request_: ClefRequest, clef_fixture: dict[str, Any]) -> None:
    del clef_fixture["result"]["answers"]["severity"]
    with pytest.raises(ClefResponseError, match="unanswered"):
        await backend(_ok(clef_fixture)).run(request_)


@pytest.mark.parametrize(
    "fixture,status,needle",
    [
        ("error_missing_instructions", 400, "required properties"),
        ("error_model_mismatch", 422, "Unsupported model"),
        ("error_one_option", 422, "at least 2 items"),
    ],
)
async def test_recorded_error_responses(
    request_: ClefRequest, fixture: str, status: int, needle: str
) -> None:
    payload = json.loads((Path(__file__).parent / f"fixtures/workers_ai/{fixture}.json").read_text())
    calls = {"n": 0}

    def handler(r: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(status, json=payload)

    with pytest.raises(ClefRequestError, match=needle):
        await backend(handler).run(request_)
    assert calls["n"] == 1
    with pytest.raises(ClefRequestError, match="Workers AI error"):
        from debugassist.decisions.schema import parse_response

        parse_response(payload)


def _ok(payload: dict[str, Any]) -> Any:
    def handler(r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return handler
