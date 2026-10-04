import importlib
import io
import json
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture
def client(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("BUGDROP_DATABASE_URL", f"sqlite:///{tmp_path}/b.db")
    monkeypatch.setenv("BUGDROP_FILES_DIR", str(tmp_path / "files"))
    monkeypatch.delenv("BUGDROP_S3_ENDPOINT", raising=False)
    monkeypatch.delenv("BUGDROP_WEBHOOK_URL", raising=False)
    import bugdrop_service.app as app_module

    importlib.reload(app_module)
    with TestClient(app_module.app) as c:
        yield c


def png(color: str = "white") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 80), color).save(buf, format="PNG")
    return buf.getvalue()


def submit(c: TestClient, **over: Any) -> dict[str, Any]:
    now = time.time()
    report = {
        "description": "MiniRide is using 30% of my battery, phone heating up. mail me: jo@example.com",
        "app": "miniride-client",
        "version": "1.6.0",
        "session_id": "s1",
        "device": {"os": "Android 15", "browser": "Chrome 141", "device": "Pixel 7", "locale": "en-US"},
        "city": "sf",
        "route": "/ride/abc",
        "flags": {"notif_router_v2": False},
        "network": {"effectiveType": "4g", "rtt": 50},
        "logs": {
            "ui_state": [
                {"ts": now - 1100, "route": "/ride/abc", "visibility": "visible"},
                {"ts": now - 1020, "route": "/ride/abc", "visibility": "hidden"},
                {"ts": now - 600, "route": "/ride/abc", "visibility": "hidden"},
                {"ts": now - 0.5, "route": "/ride/abc", "visibility": "visible"},
            ],
            "network": [
                {
                    "ts": now - 5,
                    "method": "POST",
                    "url": "http://gw/graphql",
                    "status": 200,
                    "ms": 40,
                    "body": "token=sk-live_ABCDEFGHIJ1234567890",
                }
            ],
            "analytics": [{"ts": now - 10 + i * 0.001, "name": "eta_background_tick"} for i in range(400)],
        },
        "created_at": now,
        **over,
    }
    files = [
        ("screenshot", ("app.png", png(), "image/png")),
        ("attachments", ("battery.png", png("black"), "image/png")),
    ]
    r = c.post("/v1/reports", data={"report": json.dumps(report)}, files=files)
    assert r.status_code == 201, r.text
    return r.json()


def test_report_round_trip(client: TestClient) -> None:
    out = submit(client)
    assert out["id"] == "BD-1001"
    assert "[email]" in out["description"] and "jo@example.com" not in out["description"]
    assert out["log_counts"]["analytics"] == 400 and out["log_counts"]["console"] == 0
    shots = client.get(f"/api/reports/{out['id']}/screenshots").json()
    assert [s["kind"] for s in shots] == ["app_screenshot", "user_attachment"]
    img = client.get(shots[1]["url"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    net = client.get(f"/api/reports/{out['id']}/logs", params={"kind": "network"}).json()
    assert "[token]" in net["entries"][0]["body"]
    burst = client.get(
        f"/api/reports/{out['id']}/logs", params={"kind": "analytics", "q": "eta_background", "limit": 5}
    ).json()
    assert burst["total"] == 400 and len(burst["entries"]) == 5
    tl = client.get(f"/api/reports/{out['id']}/ui-state-timeline").json()
    assert tl["longest_hidden_s"] == pytest.approx(1019.5, abs=1)  # ~17 minutes
    assert [i["state"] for i in tl["visibility"]] == ["visible", "hidden", "visible"]
    assert client.get(f"/reports/{out['id']}").status_code == 200
    assert out["id"] in client.get("/").text


def test_rejects_non_images(client: TestClient) -> None:
    r = client.post(
        "/v1/reports",
        data={"report": json.dumps({"description": "x", "app": "a", "version": "1"})},
        files=[("attachments", ("evil.html", b"<script>", "image/png"))],
    )
    assert r.status_code == 415


def test_bad_log_kind(client: TestClient) -> None:
    rid = submit(client)["id"]
    assert client.get(f"/api/reports/{rid}/logs", params={"kind": "secrets"}).status_code == 400
