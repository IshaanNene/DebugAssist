"""Idempotently create MiniRide's feature flags in the local Unleash (stdlib only).

Every flag gets a gradual-rollout strategy with sessionId stickiness in the `development`
environment. Rollout percentages are the "release state" of v1.4.0; bug scenarios change them
later through the feature-flags tooling, not here.

    python infra/unleash/bootstrap.py [--url http://localhost:4242]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

ADMIN_TOKEN = "*:*.unleash-insecure-admin-api-token"  # noqa: S105 - Unleash documented local-dev token
PROJECT, ENV = "default", "development"

FLAGS = [
    {
        "name": "notif_router_v2",
        "description": "Notification deep-link router v2 (prefills the ride screen). Client.",
        "rollout": 0,
    },
    {
        "name": "surge_pricing",
        "description": "Apply surge multiplier to fares when demand is high. Payments.",
        "rollout": 0,
    },
]


def call(base: str, method: str, path: str, body: object | None = None) -> tuple[int, object]:
    req = urllib.request.Request(  # noqa: S310 - base URL is a local http(s) Unleash
        base + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": ADMIN_TOKEN, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def ensure_flag(base: str, flag: dict[str, object]) -> None:
    name = flag["name"]
    status, _ = call(base, "GET", f"/api/admin/projects/{PROJECT}/features/{name}")
    if status == 404:
        status, body = call(
            base,
            "POST",
            f"/api/admin/projects/{PROJECT}/features",
            {"name": name, "type": "release", "description": flag["description"]},
        )
        if status >= 300:
            sys.exit(f"create {name}: {status} {body}")
        print(f"created {name}")
    status, strategies = call(
        base, "GET", f"/api/admin/projects/{PROJECT}/features/{name}/environments/{ENV}/strategies"
    )
    if status >= 300:
        sys.exit(f"strategies {name}: {status} {strategies}")
    if not any(s.get("name") == "flexibleRollout" for s in strategies or []):  # type: ignore[union-attr]
        params = {"rollout": str(flag["rollout"]), "stickiness": "sessionId", "groupId": name}
        status, body = call(
            base,
            "POST",
            f"/api/admin/projects/{PROJECT}/features/{name}/environments/{ENV}/strategies",
            {"name": "flexibleRollout", "parameters": params, "constraints": []},
        )
        if status >= 300:
            sys.exit(f"add strategy {name}: {status} {body}")
        print(f"{name}: gradual rollout {flag['rollout']}% (sessionId)")
    status, body = call(base, "POST", f"/api/admin/projects/{PROJECT}/features/{name}/environments/{ENV}/on")
    if status >= 300:
        sys.exit(f"enable {name}: {status} {body}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:4242")
    base = ap.parse_args().url.rstrip("/")
    for f in FLAGS:
        ensure_flag(base, f)
    print("unleash flags ready")


if __name__ == "__main__":
    main()
