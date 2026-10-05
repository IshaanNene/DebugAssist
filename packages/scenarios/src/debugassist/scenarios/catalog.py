"""Ground-truth bug catalog models (`groundtruth/bugs/*.yaml`)."""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

# The repository checkout. Packaged runs (PEX in a runtime image) point it at the mounted checkout.
ROOT = Path(os.environ.get("DEBUGASSIST_ROOT") or Path(__file__).resolve().parents[5])
GROUNDTRUTH = ROOT / "groundtruth"

Category = Literal["own_code", "third_party_lib", "infra", "network", "flag_config", "device_os", "not_a_bug"]
Tier = Literal["unit", "integration", "e2e_env", "cannot_repro"]
Outcome = Literal["pr", "rca_only", "route"]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Toxic(_M):
    proxy: str
    name: str
    type: str
    stream: Literal["upstream", "downstream"] = "downstream"
    toxicity: float = 1.0
    attributes: dict[str, Any] = Field(default_factory=dict[str, Any])


class IncidentSpec(_M):
    title: str
    severity: Literal["sev1", "sev2", "sev3"] = "sev2"
    services: list[str] = Field(default_factory=list[str])
    owner_team: str | None = None
    commander: str | None = None
    summary: str = ""


class Injection(_M):
    base: str = "v1.5.0"
    release: str | None = None
    repos: dict[str, list[str]] = Field(default_factory=dict[str, list[str]])
    flags: dict[str, int] = Field(default_factory=dict[str, int])
    toxics: list[Toxic] = Field(default_factory=list[Toxic])
    incidents: list[IncidentSpec] = Field(default_factory=list[IncidentSpec])
    dependencies: dict[str, str] = Field(default_factory=dict[str, str])


class Trigger(_M):
    scenario: str
    params: dict[str, Any] = Field(default_factory=dict[str, Any])


class HiddenTest(_M):
    src: str
    repo: str
    dest: str


class Location(_M):
    repo: str | None
    module: str | None
    file: str | None
    function: str | None


class GroundTruth(_M):
    fix: str | None
    hidden_tests: list[HiddenTest] = Field(default_factory=list[HiddenTest])
    location: Location
    rca_facts: list[str]
    mitigation: str | dict[str, str] = "none"


class Validation(_M):
    cheapest_tier: Tier
    e2e: str | None = None


class Bug(_M):
    id: str
    title: str
    language: str
    component: str
    owner_team: str
    category: Category
    priority: Literal["P0", "P1", "P2", "P3", "P4"]
    discovery: list[Literal["bugdrop", "vitals"]]
    injection: Injection
    trigger: Trigger
    ground_truth: GroundTruth
    validation: Validation
    expected_outcome: Outcome
    route_to: str | None = None

    def path(self, rel: str) -> Path:
        return GROUNDTRUTH / rel


@cache
def load_catalog(directory: Path | None = None) -> dict[str, Bug]:
    directory = directory or GROUNDTRUTH / "bugs"
    bugs: dict[str, Bug] = {}
    for p in sorted(directory.glob("BUG-*.yaml")):
        bug = Bug.model_validate(yaml.safe_load(p.read_text()))
        if bug.id != p.stem:
            raise ValueError(f"{p.name}: id {bug.id} must match the file name")
        bugs[bug.id] = bug
    return bugs


def get_bug(bug_id: str) -> Bug:
    key = bug_id if bug_id.startswith("BUG-") else f"BUG-{int(bug_id):03d}"
    catalog = load_catalog()
    if key not in catalog:
        raise KeyError(f"unknown bug {bug_id}; known: {sorted(catalog)}")
    return catalog[key]
