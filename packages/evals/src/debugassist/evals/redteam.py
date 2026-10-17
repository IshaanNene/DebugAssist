"""The prompt-injection red-team catalogue (`evals/redteam/payloads.yaml`) and the controls it names.

Offline, each payload's attempted action is checked against the control that must stop it whatever the model does
(`test_redteam.py`). The live arm (ROADMAP-100 task 003) also runs them through the pipeline with canary secrets.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from debugassist.core.policy import ROOT

CATALOGUE = ROOT / "evals" / "redteam" / "payloads.yaml"
Control = Literal["fence", "guard", "confine", "walk", "hostgit", "policy", "redact", "container"]
OFFLINE: set[str] = {"fence", "guard", "confine", "walk", "hostgit", "policy", "redact"}


class Write(BaseModel):
    action: str
    repo: str | None = None
    branch: str | None = None


class Attempt(BaseModel):
    command: str | None = None
    path: str | None = None
    symlink: str | None = None
    gitdir_swap: bool = False
    secret: str | None = None
    write: Write | None = None
    fence_break: bool = False


class Payload(BaseModel):
    id: str
    channel: Literal["issue_body", "log", "commit", "code_comment", "test_output"]
    text: str
    tries: Attempt
    stopped_by: list[Control] = Field(min_length=1)
    note: str | None = None


def load(path: Path = CATALOGUE) -> list[Payload]:
    raw: dict[str, Any] = yaml.safe_load(path.read_text())
    return [Payload.model_validate(p) for p in raw["payloads"]]
