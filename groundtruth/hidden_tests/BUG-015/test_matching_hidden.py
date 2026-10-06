"""Hidden test for BUG-015 (never committed to the target repo). Copied to dispatch/tests/ at eval time."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DISPATCH_DATABASE_URL", f"sqlite:///{tmp_path}/h.db")
    monkeypatch.setenv("DISPATCH_MATCH_DELAY_MS", "0")
    import importlib

    import dispatch.app as app_module

    importlib.reload(app_module)
    with TestClient(app_module.app) as c:
        yield c


def req(i: int) -> dict[str, object]:
    return {
        "session_id": f"s-{i}",
        "city": "sf",
        "pickup": {"name": "Ferry Building", "lat": 37.7955, "lng": -122.3937},
        "dropoff": {"name": "SFO Airport", "lat": 37.6213, "lng": -122.3790},
    }


def test_rides_are_only_matched_with_drivers_in_the_same_city(client: TestClient) -> None:
    statuses: list[int] = []
    for i in range(14):  # more requests than San Francisco has drivers
        r = client.post("/rides", json=req(i))
        statuses.append(r.status_code)
        if r.status_code == 201:
            assert r.json()["driver"]["id"].startswith("sf-"), r.json()["driver"]
    assert statuses.count(201) >= 1 and statuses[-1] == 409  # sold out → "no drivers", never another city
