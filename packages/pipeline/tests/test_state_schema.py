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


def test_failures_are_typed_and_old_errors_are_converted() -> None:
    """ROADMAP-100 034: v2 state files' `errors` pairs become NodeFailure records."""
    raw: dict[str, Any] = json.loads(FIXTURE.read_text())
    raw["schema_version"] = 2
    raw.pop("failures", None)
    raw["errors"] = [
        "fix: RuntimeError: base branch release/1.6.1 is not on GitHub",
        "Traceback (most recent…)",
    ]
    s = RunState.model_validate(raw)
    [f] = s.failures
    assert (f.node, f.type, f.message) == (
        "fix",
        "RuntimeError",
        "base branch release/1.6.1 is not on GitHub",
    )
    assert f.traceback.startswith("Traceback")


def test_a_failing_node_records_a_typed_failure() -> None:
    import asyncio
    from typing import cast

    from debugassist.pipeline.graph import _run_node  # pyright: ignore[reportPrivateUsage]

    async def boom(state: RunState, deps: Any) -> dict[str, Any]:
        raise ValueError("no such tag v9")

    update = asyncio.run(
        _run_node(
            "ingest",
            "deterministic",
            boom,
            RunState(run_id="r", issue_ref="x"),
            cast(Any, None),
            lambda _: None,
        )
    )
    [f] = update["failures"]
    assert (f.node, f.type, f.message) == (
        "ingest",
        "ValueError",
        "no such tag v9",
    ) and "ValueError" in f.traceback
