"""Runtime controls of the local stack: Unleash rollouts, Toxiproxy toxics, incidents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from debugassist.scenarios.catalog import IncidentSpec, Toxic

UNLEASH_ADMIN_TOKEN = "*:*.unleash-insecure-admin-api-token"  # noqa: S105 - Unleash local-dev token
BASELINE_FLAGS = {"notif_router_v2": 0, "surge_pricing": 0}


@dataclass(frozen=True)
class Endpoints:
    unleash: str = "http://localhost:4242"
    toxiproxy: str = "http://localhost:8474"
    incidents: str = "http://localhost:8300"
    vitals: str = "http://localhost:8100"
    bugdrop: str = "http://localhost:8200"
    gateway: str = "http://localhost:4000"
    dispatch: str = "http://localhost:8001"


class Environment:
    def __init__(self, endpoints: Endpoints | None = None, client: httpx.Client | None = None) -> None:
        self.ep = endpoints or Endpoints()
        self.http = client or httpx.Client(timeout=10)

    # ---- Unleash ----------------------------------------------------------------------------
    def set_rollout(self, flag: str, percent: int) -> None:
        base = f"{self.ep.unleash}/api/admin/projects/default/features/{flag}/environments/development"
        h = {"Authorization": UNLEASH_ADMIN_TOKEN}
        strategies: list[dict[str, Any]] = (
            self.http.get(f"{base}/strategies", headers=h).raise_for_status().json()
        )
        rollout = next((s for s in strategies if s["name"] == "flexibleRollout"), None)
        if rollout is None:
            raise RuntimeError(f"{flag}: no gradual rollout strategy (run `make flags`)")
        params = {**rollout.get("parameters", {}), "rollout": str(percent)}
        self.http.put(
            f"{base}/strategies/{rollout['id']}",
            headers=h,
            json={
                "name": "flexibleRollout",
                "parameters": params,
                "constraints": rollout.get("constraints", []),
            },
        ).raise_for_status()

    def rollout(self, flag: str) -> int:
        base = f"{self.ep.unleash}/api/admin/projects/default/features/{flag}/environments/development"
        strategies = self.http.get(
            f"{base}/strategies", headers={"Authorization": UNLEASH_ADMIN_TOKEN}
        ).json()
        s = next((s for s in strategies if s["name"] == "flexibleRollout"), None)
        return int(s["parameters"]["rollout"]) if s else 0

    # ---- Toxiproxy --------------------------------------------------------------------------
    def add_toxic(self, t: Toxic) -> None:
        body = {
            "name": t.name,
            "type": t.type,
            "stream": t.stream,
            "toxicity": t.toxicity,
            "attributes": t.attributes,
        }
        r = self.http.post(f"{self.ep.toxiproxy}/proxies/{t.proxy}/toxics", json=body)
        if r.status_code == 409:  # already present: replace
            self.http.delete(f"{self.ep.toxiproxy}/proxies/{t.proxy}/toxics/{t.name}")
            r = self.http.post(f"{self.ep.toxiproxy}/proxies/{t.proxy}/toxics", json=body)
        r.raise_for_status()

    def clear_toxics(self) -> None:
        self.http.post(f"{self.ep.toxiproxy}/reset").raise_for_status()

    # ---- incidents --------------------------------------------------------------------------
    def declare_incident(self, i: IncidentSpec) -> str:
        return str(
            self.http.post(f"{self.ep.incidents}/api/incidents", json=i.model_dump())
            .raise_for_status()
            .json()["id"]
        )

    def set_dependency(self, name: str, status: str) -> None:
        self.http.put(
            f"{self.ep.incidents}/api/dependencies/{name}", params={"status": status}
        ).raise_for_status()

    def reset_incidents(self) -> None:
        self.http.post(f"{self.ep.incidents}/api/reset").raise_for_status()

    # ---- discovery sources --------------------------------------------------------------------
    def vitals_issues(self) -> list[dict[str, Any]]:
        return self.http.get(f"{self.ep.vitals}/api/issues", params={"limit": 200}).raise_for_status().json()

    def bugdrop_reports(self) -> list[dict[str, Any]]:
        return (
            self.http.get(f"{self.ep.bugdrop}/api/reports", params={"limit": 200}).raise_for_status().json()
        )

    def baseline(self) -> None:
        for flag, pct in BASELINE_FLAGS.items():
            self.set_rollout(flag, pct)
        self.clear_toxics()
        self.reset_incidents()
