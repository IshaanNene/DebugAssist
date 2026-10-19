# Hidden test for BUG-027 (never committed to the target repo). Copied to dispatch/tests/ at eval time.
from __future__ import annotations

import importlib
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SF_REQ = {
    "session_id": "s-1",
    "city": "sf",
    "pickup": {"name": "Ferry Building", "lat": 37.7955, "lng": -122.3937},
    "dropoff": {"name": "SFO Airport", "lat": 37.6213, "lng": -122.3790},
}

# The drivers table as the previous release created it, with its fleet already seeded.
OLD_DRIVERS = """
CREATE TABLE drivers (
    id VARCHAR(32) NOT NULL PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    city VARCHAR(16) NOT NULL,
    lat FLOAT,
    lng FLOAT,
    vehicle VARCHAR(32) NOT NULL,
    rating FLOAT NOT NULL,
    busy_ride_id VARCHAR(36)
)
"""


def _existing_db(path: Path, extra: str = "") -> None:
    con = sqlite3.connect(path)
    con.execute(OLD_DRIVERS)
    con.executemany(
        "INSERT INTO drivers (id, name, city, lat, lng, vehicle, rating) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("sf-d00", "Ana A.", "sf", 37.79, -122.40, "Toyota Prius", 4.9),
            ("sf-d01", "Ben B.", "sf", 37.78, -122.41, "Honda Fit", 4.7),
        ],
    )
    if extra:
        con.execute(extra)
    con.commit()
    con.close()


def _client(path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DISPATCH_DATABASE_URL", f"sqlite:///{path}")
    monkeypatch.setenv("DISPATCH_MATCH_DELAY_MS", "0")
    import dispatch.app as app_module

    importlib.reload(app_module)
    with TestClient(app_module.app) as c:
        yield c


def test_drivers_from_before_the_upgrade_are_still_matched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _existing_db(tmp_path / "t.db")
    for client in _client(tmp_path / "t.db", monkeypatch):
        r = client.post("/rides", json=SF_REQ)
        assert r.status_code == 201, r.text
        assert r.json()["driver"]["id"] in {"sf-d00", "sf-d01"}


def test_a_database_already_upgraded_once_recovers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The column was added earlier without a value for the existing drivers.
    _existing_db(tmp_path / "t.db", extra="ALTER TABLE drivers ADD COLUMN online BOOLEAN")
    for client in _client(tmp_path / "t.db", monkeypatch):
        r = client.post("/rides", json=SF_REQ)
        assert r.status_code == 201, r.text
