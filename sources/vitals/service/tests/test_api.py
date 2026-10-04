import importlib
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("VITALS_DATABASE_URL", f"sqlite:///{tmp_path}/v.db")
    monkeypatch.delenv("VITALS_WEBHOOK_URL", raising=False)
    import vitals_service.app as app_module

    importlib.reload(app_module)
    with TestClient(app_module.app) as c:
        yield c


STACK = "TypeError: Cannot read properties of undefined (reading 'riderId')\n    at Kt (http://localhost:8080/assets/index-D4kq9Xa1.js:1:5)"


def session(c: TestClient, sid: str, v2: bool, version: str = "1.6.1", city: str = "sf") -> None:
    c.post(
        "/v1/sessions",
        json={
            "session_id": sid,
            "app": "miniride-client",
            "version": version,
            "flags": {"notif_router_v2": v2},
            "device": {"os": "Android 15", "browser": "Chrome 141", "city": city},
        },
    ).raise_for_status()


def crash(c: TestClient, sid: str, version: str = "1.6.1") -> dict[str, Any]:
    r = c.post(
        "/v1/events",
        json={
            "events": [
                {
                    "event_id": str(uuid.uuid4()),
                    "kind": "crash",
                    "app": "miniride-client",
                    "platform": "web",
                    "version": version,
                    "ts": time.time(),
                    "session_id": sid,
                    "error": {
                        "type": "TypeError",
                        "message": "Cannot read properties of undefined (reading 'riderId')",
                        "stack": STACK,
                    },
                    "breadcrumbs": [
                        {"ts": time.time(), "category": "navigation", "message": "launch from push"}
                    ],
                    "flags": {"notif_router_v2": True},
                }
            ]
        },
    )
    r.raise_for_status()
    return r.json()


def test_crash_opens_issue_with_flag_exposure(client: TestClient) -> None:
    for i in range(100):
        session(client, f"s{i}", v2=i < 5)  # 5% rollout
    for i in range(3):
        crash(client, f"s{i}")
    issues = client.get("/api/issues", params={"status": "open"}).json()
    assert len(issues) == 1
    issue = issues[0]
    assert issue["id"] == "VIT-1001" and issue["reason"] == "new" and issue["group"]["count"] == 3
    fp = issue["fingerprint"]
    flags = client.get(f"/api/groups/{fp}/flags").json()
    f = next(x for x in flags if x["flag"] == "notif_router_v2")
    assert f["exposed_share_of_sessions"] == pytest.approx(0.05)
    assert f["exposed_share_of_affected"] == 1.0
    assert f["rate_exposed"] == pytest.approx(0.6) and f["rate_unexposed"] == 0.0
    by_version = client.get(f"/api/groups/{fp}/distribution", params={"by": "version"}).json()
    assert by_version["values"][0]["value"] == "1.6.1"
    detail = client.get(f"/api/issues/{issue['id']}").json()
    assert detail["latest_event"]["breadcrumbs"][0]["message"] == "launch from push"
    assert client.get(f"/issues/{issue['id']}").status_code == 200
    assert "VIT-1001" in client.get("/").text


def test_regression_reopens_resolved_issue_on_newer_version(client: TestClient) -> None:
    session(client, "a", True)
    crash(client, "a", version="1.6.1")
    issue_id = client.get("/api/issues").json()[0]["id"]
    client.post(f"/api/issues/{issue_id}/resolve", params={"version": "1.6.2"}).raise_for_status()
    crash(client, "a", version="1.6.2")  # old build still around → not a regression
    assert client.get(f"/api/issues/{issue_id}").json()["status"] == "resolved"
    crash(client, "a", version="1.7.0")
    reopened = client.get(f"/api/issues/{issue_id}").json()
    assert (reopened["status"], reopened["reason"]) == ("open", "regression")


def test_jank_needs_repeated_evidence(client: TestClient) -> None:
    def jank() -> None:
        client.post(
            "/v1/events",
            json={
                "events": [
                    {
                        "event_id": str(uuid.uuid4()),
                        "kind": "jank",
                        "app": "miniride-client",
                        "platform": "web",
                        "version": "1.6.0",
                        "ts": time.time(),
                        "culprit": "/ride/abc",
                        "perf": {"metric": "long_tasks", "value": 12},
                    }
                ]
            },
        ).raise_for_status()

    jank()
    jank()
    assert client.get("/api/issues").json() == []
    jank()
    assert len(client.get("/api/issues").json()) == 1


def test_backend_exception_with_structured_frames(client: TestClient) -> None:
    client.post(
        "/v1/events",
        json={
            "events": [
                {
                    "event_id": "e-py-1",
                    "kind": "exception",
                    "app": "dispatch",
                    "platform": "python",
                    "version": "1.6.3",
                    "ts": time.time(),
                    "culprit": "GET /rides/{ride_id}/eta",
                    "error": {
                        "type": "TypeError",
                        "message": "unsupported operand type(s) for -: 'NoneType' and 'float'",
                        "frames": [
                            {"function": "get_eta", "file": "dispatch/app.py", "line": 210},
                            {"function": "eta_seconds", "file": "dispatch/matching.py", "line": 61},
                        ],
                    },
                }
            ]
        },
    ).raise_for_status()
    # idempotent re-delivery
    client.post(
        "/v1/events",
        json={
            "events": [
                {
                    "event_id": "e-py-1",
                    "kind": "exception",
                    "app": "dispatch",
                    "platform": "python",
                    "version": "1.6.3",
                    "ts": time.time(),
                    "error": {"type": "TypeError", "message": "x", "frames": list[dict[str, str]]()},
                }
            ]
        },
    ).raise_for_status()
    issue = client.get("/api/issues").json()[0]
    assert issue["group"]["count"] == 1
    assert issue["group"]["culprit"] == "GET /rides/{ride_id}/eta"
    ev = client.get(f"/api/issues/{issue['id']}").json()["latest_event"]
    assert ev["frames"][-1]["function"] == "eta_seconds"
