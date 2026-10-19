# Hidden test for BUG-026 (never committed to the target repo). Copied to dispatch/tests/ at eval time.
from __future__ import annotations

import importlib
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DISPATCH_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("DISPATCH_MATCH_DELAY_MS", "300")  # real matching takes time; requests overlap
    import dispatch.app as app_module

    importlib.reload(app_module)
    with TestClient(app_module.app) as c:
        yield c


def _request(client: TestClient, i: int) -> dict:  # type: ignore[type-arg]
    body = {
        "session_id": f"s-{i}",
        "city": "sf",
        "pickup": {"name": "Ferry Building", "lat": 37.7955, "lng": -122.3937},
        "dropoff": {"name": "SFO Airport", "lat": 37.6213, "lng": -122.3790},
    }
    r = client.post("/rides", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_riders_booking_at_the_same_time_get_different_drivers(client: TestClient) -> None:
    # Riders a tenth of a second apart, each request still matching while the next one arrives.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = []
        for i in range(4):
            futures.append(pool.submit(_request, client, i))
            time.sleep(0.1)
        rides = [f.result() for f in futures]
    drivers = [r["driver"]["id"] for r in rides]
    assert len(set(drivers)) == len(drivers), f"one driver assigned to several riders: {drivers}"
