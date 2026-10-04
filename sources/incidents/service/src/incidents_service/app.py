"""Incident tracker: what is broken right now, who is on it, and third-party provider status.

State is a small JSON file (it changes rarely and is driven by humans or scenario tooling).
"""

from __future__ import annotations

import copy
import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

STATE = Path(os.environ.get("INCIDENTS_STATE_FILE", "./incidents.json"))
_lock = threading.Lock()

DEFAULT_DEPENDENCIES = {
    "maps-provider": {"description": "Geocoding and routing API", "status": "operational"},
    "payment-processor": {"description": "Card authorization network", "status": "operational"},
    "push-provider": {"description": "Mobile push delivery", "status": "operational"},
    "sms-provider": {"description": "SMS OTP delivery", "status": "operational"},
}

Severity = Literal["sev1", "sev2", "sev3"]
DepStatus = Literal["operational", "degraded", "partial_outage", "major_outage"]


class IncidentIn(BaseModel):
    title: str = Field(min_length=3)
    severity: Severity = "sev2"
    services: list[str] = Field(default_factory=list[str])
    summary: str = ""
    commander: str | None = None
    owner_team: str | None = None


class UpdateIn(BaseModel):
    message: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _load() -> dict[str, Any]:
    if STATE.is_file():
        return json.loads(STATE.read_text())
    return {"seq": 100, "incidents": {}, "dependencies": copy.deepcopy(DEFAULT_DEPENDENCIES)}


def _save(state: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2))


app = FastAPI(title="Incidents")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/incidents")
def list_incidents(status: Literal["active", "resolved"] | None = None) -> list[dict[str, Any]]:
    items = list(_load()["incidents"].values())
    if status:
        items = [i for i in items if i["status"] == status]
    return sorted(items, key=lambda i: i["started_at"], reverse=True)


@app.get("/api/incidents/{iid}")
def get_incident(iid: str) -> dict[str, Any]:
    inc = _load()["incidents"].get(iid)
    if inc is None:
        raise HTTPException(404, "incident not found")
    return inc


@app.post("/api/incidents", status_code=201)
def declare(body: IncidentIn) -> dict[str, Any]:
    with _lock:
        state = _load()
        state["seq"] += 1
        iid = f"INC-{state['seq']}"
        inc = {
            "id": iid,
            "status": "active",
            "started_at": _now(),
            "resolved_at": None,
            "updates": [{"at": _now(), "message": body.summary or body.title}],
            **body.model_dump(),
        }
        state["incidents"][iid] = inc
        _save(state)
    return inc


@app.post("/api/incidents/{iid}/updates")
def add_update(iid: str, body: UpdateIn) -> dict[str, Any]:
    with _lock:
        state = _load()
        inc = state["incidents"].get(iid)
        if inc is None:
            raise HTTPException(404, "incident not found")
        inc["updates"].append({"at": _now(), "message": body.message})
        _save(state)
    return inc


@app.post("/api/incidents/{iid}/resolve")
def resolve(iid: str) -> dict[str, Any]:
    with _lock:
        state = _load()
        inc = state["incidents"].get(iid)
        if inc is None:
            raise HTTPException(404, "incident not found")
        inc["status"], inc["resolved_at"] = "resolved", _now()
        _save(state)
    return inc


@app.get("/api/dependencies")
def dependencies() -> dict[str, Any]:
    return _load()["dependencies"]


@app.put("/api/dependencies/{name}")
def set_dependency(name: str, status: DepStatus, note: str = "") -> dict[str, Any]:
    with _lock:
        state = _load()
        dep = state["dependencies"].setdefault(name, {"description": name, "status": "operational"})
        dep["status"], dep["note"], dep["updated_at"] = status, note, _now()
        _save(state)
    return dep


@app.post("/api/reset")
def reset() -> dict[str, str]:
    """Scenario tooling: forget all incidents and restore dependency status."""
    with _lock:
        _save({"seq": 100, "incidents": {}, "dependencies": copy.deepcopy(DEFAULT_DEPENDENCIES)})
    return {"status": "reset"}
