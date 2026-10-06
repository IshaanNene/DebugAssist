"""Hidden test for BUG-016 (never committed to the target repo). Copied to dispatch/tests/ at eval time."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DISPATCH_DATABASE_URL", f"sqlite:///{tmp_path}/h.db")
    import importlib

    import dispatch.app as app_module

    importlib.reload(app_module)
    with TestClient(app_module.app) as c:
        yield c


@pytest.mark.parametrize("city", ["sf", "nyc", "blr", "tokyo"])
def test_every_city_lists_its_places(client: TestClient, city: str) -> None:
    r = client.get("/places", params={"city": city})
    assert r.status_code == 200
    assert len(r.json()) >= 3
