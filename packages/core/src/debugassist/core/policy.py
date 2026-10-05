"""Write-action policy gate and audit log.

Every side effect outside the sandbox (tickets, PRs, pushes, chat, flag changes) asks the gate
first and is written to the audit log whatever the verdict.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

# The repository checkout. Packaged runs (PEX in a runtime image) point it at the mounted checkout.
ROOT = Path(os.environ.get("DEBUGASSIST_ROOT") or Path(__file__).resolve().parents[5])
DEFAULT_POLICY = ROOT / "configs" / "policies" / "writes.yaml"
DEFAULT_AUDIT = ROOT / ".data" / "audit.jsonl"


class Verdict(StrEnum):
    LIVE = "live"
    DRY_RUN = "dry_run"
    APPROVAL = "approval"
    DENY = "deny"


class Policy(BaseModel):
    version: int = 1
    actions: dict[str, Verdict] = Field(default_factory=dict[str, Verdict])
    repos: list[str] = Field(default_factory=list[str])
    branches: dict[str, str] = Field(default_factory=dict[str, str])

    @classmethod
    def load(cls, path: Path = DEFAULT_POLICY) -> Policy:
        return cls.model_validate(yaml.safe_load(path.read_text()))


class PolicyError(PermissionError):
    pass


class PolicyGate:
    def __init__(
        self, policy: Policy | None = None, audit_path: Path = DEFAULT_AUDIT, *, mode: str = "autonomous"
    ) -> None:
        self.policy = policy or Policy.load()
        self.audit_path = audit_path
        self.mode = mode  # autonomous | supervised

    def verdict(self, action: str, *, repo: str | None = None, branch: str | None = None) -> Verdict:
        v = self.policy.actions.get(action, Verdict.DRY_RUN)
        if repo is not None and repo not in self.policy.repos:
            return Verdict.DENY
        if branch is not None:
            prefix = self.policy.branches.get("push_prefix", "debugassist/")
            if not branch.startswith(prefix) or re.search(r"\.\.|[~^:\\\s]", branch):
                return Verdict.DENY
        if v is Verdict.APPROVAL and self.mode == "autonomous":
            return Verdict.DRY_RUN
        return v

    def record(
        self, action: str, verdict: Verdict, *, run_id: str | None, detail: dict[str, Any], result: Any = None
    ) -> None:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "at": datetime.now(UTC).isoformat(),
            "run_id": run_id,
            "action": action,
            "verdict": verdict.value,
            "detail": detail,
            "result": result,
        }
        with self.audit_path.open("a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
