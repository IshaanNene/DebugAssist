"""Roadmap 061: run state carries a schema version; older files are upgraded on load, newer ones refused."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from debugassist.pipeline.state import SCHEMA_VERSION, RunState

FIXTURE = Path(__file__).parent / "fixtures" / "run_state.json"


def test_a_stored_v1_file_loads_and_is_upgraded() -> None:
    raw: dict[str, Any] = json.loads(FIXTURE.read_text())
    raw.pop("schema_version", None)
    raw |= {"status": "stopped", "stopped_after": None, "timings_ms": {"ingest": 3, "auto_triage": 9}}
    s = RunState.model_validate(raw)
    assert s.schema_version == SCHEMA_VERSION and s.stopped_after == "auto_triage"
    assert json.loads(s.model_dump_json())["schema_version"] == SCHEMA_VERSION


def test_a_newer_file_is_refused() -> None:
    raw: dict[str, Any] = json.loads(FIXTURE.read_text())
    raw["schema_version"] = SCHEMA_VERSION + 1
    with pytest.raises(ValueError, match="newer than this DebugAssist"):
        RunState.model_validate(raw)
