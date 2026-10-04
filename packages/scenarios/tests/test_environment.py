import json
from typing import Any

import httpx

from debugassist.scenarios.catalog import IncidentSpec, Toxic
from debugassist.scenarios.environment import Environment


def make(handler: Any) -> Environment:
    return Environment(client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_set_rollout_updates_the_gradual_rollout_strategy() -> None:
    seen: list[httpx.Request] = []

    def handler(r: httpx.Request) -> httpx.Response:
        seen.append(r)
        if r.method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "s1",
                        "name": "flexibleRollout",
                        "parameters": {
                            "rollout": "0",
                            "stickiness": "sessionId",
                            "groupId": "notif_router_v2",
                        },
                        "constraints": [],
                    }
                ],
            )
        return httpx.Response(200, json={})

    make(handler).set_rollout("notif_router_v2", 5)
    put = seen[-1]
    assert put.method == "PUT" and put.url.path.endswith("/strategies/s1")
    body = json.loads(put.content)
    assert body["parameters"] == {"rollout": "5", "stickiness": "sessionId", "groupId": "notif_router_v2"}
    assert put.headers["authorization"].startswith("*:*.")


def test_add_toxic_replaces_existing() -> None:
    calls: list[str] = []

    def handler(r: httpx.Request) -> httpx.Response:
        calls.append(f"{r.method} {r.url.path}")
        if r.method == "POST" and len([c for c in calls if c.startswith("POST")]) == 1:
            return httpx.Response(409, json={"error": "exists"})
        return httpx.Response(200, json={})

    make(handler).add_toxic(
        Toxic(proxy="postgres", name="db_latency", type="latency", attributes={"latency": 4000})
    )
    assert calls == [
        "POST /proxies/postgres/toxics",
        "DELETE /proxies/postgres/toxics/db_latency",
        "POST /proxies/postgres/toxics",
    ]


def test_declare_incident() -> None:
    def handler(r: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"id": "INC-101", **json.loads(r.content)})

    env = make(handler)
    assert env.declare_incident(IncidentSpec(title="Postgres degraded", owner_team="sre-infra")) == "INC-101"
