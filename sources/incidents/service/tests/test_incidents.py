import importlib
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("INCIDENTS_STATE_FILE", str(tmp_path / "i.json"))
    import incidents_service.app as m

    importlib.reload(m)
    yield TestClient(m.app)


def test_incident_lifecycle(client: TestClient) -> None:
    inc = client.post(
        "/api/incidents",
        json={
            "title": "Postgres primary degraded",
            "severity": "sev1",
            "services": ["postgres", "dispatch"],
            "owner_team": "sre-infra",
        },
    ).json()
    assert inc["id"] == "INC-101" and inc["status"] == "active"
    assert [i["id"] for i in client.get("/api/incidents", params={"status": "active"}).json()] == ["INC-101"]
    client.post("/api/incidents/INC-101/updates", json={"message": "failover started"})
    client.post("/api/incidents/INC-101/resolve")
    assert client.get("/api/incidents", params={"status": "active"}).json() == []
    assert len(client.get("/api/incidents/INC-101").json()["updates"]) == 2


def test_dependencies(client: TestClient) -> None:
    assert client.get("/api/dependencies").json()["maps-provider"]["status"] == "operational"
    client.put("/api/dependencies/maps-provider", params={"status": "major_outage", "note": "429s"})
    assert client.get("/api/dependencies").json()["maps-provider"]["status"] == "major_outage"
    client.post("/api/reset")
    assert client.get("/api/dependencies").json()["maps-provider"]["status"] == "operational"
