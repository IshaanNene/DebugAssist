"""Backend load for MiniRide's gateway (GraphQL). Run with `make load`.

Riders browse places, request quotes, book rides and poll ETAs — the API-level mix behind the
Playwright fleet, at volumes a browser fleet can't reach (connection pools, N+1 queries, timeouts).
"""

from __future__ import annotations

import random
import uuid
from typing import Any

from locust import HttpUser, between, task  # pyright: ignore[reportMissingImports]

PLACES = {
    "sf": [
        ("Ferry Building", 37.7955, -122.3937),
        ("Mission Dolores Park", 37.7596, -122.4269),
        ("SFO Airport", 37.6213, -122.379),
    ],
    "nyc": [("Times Square", 40.758, -73.9855), ("JFK Airport", 40.6413, -73.7781)],
    "blr": [("MG Road", 12.9756, 77.605), ("Koramangala", 12.9352, 77.6245)],
    "tokyo": [("Shibuya Crossing", 35.6595, 139.7005), ("Shinjuku Station", 35.6896, 139.7006)],
}


def place(p: tuple[str, float, float]) -> dict[str, Any]:
    return {"name": p[0], "lat": p[1], "lng": p[2]}


class Rider(HttpUser):  # pyright: ignore[reportUntypedBaseClass]
    wait_time = between(1, 4)

    def on_start(self) -> None:
        self.session_id = str(uuid.uuid4())
        self.city = random.choice(list(PLACES))  # noqa: S311
        self.ride_id: str | None = None

    def gql(self, name: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        r = self.client.post(
            "/graphql",
            json={"operationName": name, "query": query, "variables": variables},
            headers={"x-session-id": self.session_id, "x-app-version": "load-test"},
            name=name,
        )
        return r.json() if r.ok else {}

    @task(4)
    def places(self) -> None:
        self.gql("Places", "query Places($c: String!) { places(city: $c) { name } }", {"c": self.city})

    @task(3)
    def quote(self) -> None:
        a, b = random.sample(PLACES[self.city], 2)
        self.gql(
            "FareEstimate",
            "query FareEstimate($c: String!, $p: PlaceInput!, $d: PlaceInput!) { fareEstimate(city: $c, pickup: $p, dropoff: $d) { amountCents } }",
            {"c": self.city, "p": place(a), "d": place(b)},
        )

    @task(1)
    def book(self) -> None:
        a, b = random.sample(PLACES[self.city], 2)
        out = self.gql(
            "RequestRide",
            "mutation RequestRide($i: RideInput!) { requestRide(input: $i) { id } }",
            {
                "i": {
                    "city": self.city,
                    "pickup": place(a),
                    "dropoff": place(b),
                    "idempotencyKey": str(uuid.uuid4()),
                }
            },
        )
        self.ride_id = ((out.get("data") or {}).get("requestRide") or {}).get("id") or self.ride_id

    @task(6)
    def eta(self) -> None:
        if self.ride_id:
            self.gql("Eta", "query Eta($r: ID!) { eta(rideId: $r) { etaSeconds } }", {"r": self.ride_id})
