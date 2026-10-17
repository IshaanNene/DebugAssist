"""Write-action policy gate and audit log.

Every side effect outside the sandbox (tickets, PRs, pushes, chat, flag changes) asks the gate
first and is written to the audit log whatever the verdict.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

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
    # On: a repository the GitHub App is installed on counts as allowed too (still bot branches, draft PRs).
    app_installations: bool = False
    branches: dict[str, str] = Field(default_factory=dict[str, str])

    @classmethod
    def load(cls, path: Path = DEFAULT_POLICY) -> Policy:
        return cls.model_validate(yaml.safe_load(path.read_text()))


class AuditEntry(BaseModel):
    """One line of the audit log: what was asked, the verdict, and what happened."""

    at: str = ""
    run_id: str | None = None
    action: str = ""
    verdict: str = ""
    detail: dict[str, Any] = Field(default_factory=dict[str, Any])
    result: Any = None

    @property
    def applied(self) -> bool | None:
        """True / False when the write recorded it; None for older entries that did not."""
        r: Any = self.result
        return (
            bool(cast(dict[str, Any], r).get("applied")) if isinstance(r, dict) and "applied" in r else None
        )


def read_audit(
    path: Path | None = None, run: str | None = None, action: str | None = None, last: int = 50
) -> list[AuditEntry]:
    """The audit log, newest last, filtered by run id and action prefix; lines cut short by a crash are skipped."""
    path = path or DEFAULT_AUDIT
    rows: list[AuditEntry] = []
    for line in path.read_text().splitlines() if path.is_file() else []:
        try:
            e = AuditEntry.model_validate_json(line)
        except ValueError:
            continue
        if (run is None or e.run_id == run) and (action is None or e.action.startswith(action)):
            rows.append(e)
    return rows[-last:]


class PolicyError(PermissionError):
    pass


class PolicyGate:
    def __init__(
        self,
        policy: Policy | None = None,
        audit_path: Path | None = None,
        *,
        mode: str = "autonomous",
        installed: Callable[[], list[str]] | None = None,
    ) -> None:
        self.policy = policy or Policy.load()
        self.audit_path = audit_path or DEFAULT_AUDIT  # read when the gate is made (tests point it elsewhere)
        self.mode = mode  # autonomous | supervised
        self._installed = installed  # the GitHub App's repositories, asked only when the policy allows them

    def allowed_repo(self, repo: str) -> bool:
        if repo in self.policy.repos:
            return True
        if self.policy.app_installations and self._installed is not None:
            try:
                return repo in self._installed()
            except Exception:  # the app's API unreachable: not allowed, never an accident
                return False
        return False

    def verdict(self, action: str, *, repo: str | None = None, branch: str | None = None) -> Verdict:
        v = self.policy.actions.get(action, Verdict.DRY_RUN)
        if repo is not None and not self.allowed_repo(repo):
            return Verdict.DENY
        if branch is not None:
            prefix = self.policy.branches.get("push_prefix", "debugassist/")
            if not branch.startswith(prefix) or re.search(r"\.\.|[~^:\\\s]", branch):
                return Verdict.DENY
        if v is Verdict.APPROVAL and self.mode == "autonomous":
            return Verdict.DRY_RUN
        return v

    def ready_pr_allowed(self, repo: str) -> bool:
        """Ready-for-review PRs only on the policy's own repositories; on any other (a GitHub App installation)
        a PR is always a draft, whatever a decision model proposes."""
        return repo in self.policy.repos

    def gated(
        self,
        action: str,
        perform: Callable[[], Any],
        *,
        run_id: str | None,
        detail: dict[str, Any],
        repo: str | None = None,
        branch: str | None = None,
    ) -> tuple[Verdict, Any]:
        """Ask, act only on LIVE, and audit what actually happened (also when the write fails)."""
        v = self.verdict(action, repo=repo, branch=branch)
        if v is not Verdict.LIVE:
            self.record(action, v, run_id=run_id, detail=detail, result={"applied": False})
            return v, None
        try:
            result = perform()
        except Exception as exc:
            self.record(
                action,
                v,
                run_id=run_id,
                detail=detail,
                result={"applied": False, "error": type(exc).__name__},
            )
            raise
        self.record(action, v, run_id=run_id, detail=detail, result={"applied": True, "value": result})
        return v, result

    def record(
        self, action: str, verdict: Verdict, *, run_id: str | None, detail: dict[str, Any], result: Any = None
    ) -> None:
        # Also a guardrail span in the run's trace (ROADMAP-100 060): the audit log says what was decided, the trace
        # says where in the run it happened. A no-op when tracing is off.
        from debugassist.core import tracing

        outcome: Any = result
        applied = (
            bool(cast(dict[str, Any], outcome).get("applied"))
            if isinstance(outcome, dict)
            else verdict is Verdict.LIVE
        )
        with tracing.span(
            f"gate {action}",
            kind="guardrail",
            **{"gate.action": action, "gate.verdict": verdict.value, "gate.applied": applied},
        ):
            pass
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
