"""ROADMAP-100 005 (audit P3-15): per-run values are per task, not process-wide environment variables."""

from __future__ import annotations

import asyncio
import os

import pytest

from debugassist.core import runctx


async def test_two_concurrent_runs_keep_their_own_values() -> None:
    seen: dict[str, list[str | None]] = {}

    async def run(run_id: str, repo: str) -> None:
        with runctx.use(DEBUGASSIST_RUN_ID=run_id, CODE_REPOS=repo):
            for _ in range(3):
                await asyncio.sleep(0)  # interleave with the other run
                seen.setdefault(run_id, []).append(runctx.get("CODE_REPOS"))

    await asyncio.gather(run("r1", '{"a": "/runs/r1"}'), run("r2", '{"a": "/runs/r2"}'))
    assert seen == {"r1": ['{"a": "/runs/r1"}'] * 3, "r2": ['{"a": "/runs/r2"}'] * 3}
    assert runctx.get("DEBUGASSIST_RUN_ID") == os.environ.get("DEBUGASSIST_RUN_ID")  # restored after


def test_the_environment_is_the_fallback_for_mcp_server_processes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBUGASSIST_MODE", "supervised")
    assert runctx.get("DEBUGASSIST_MODE") == "supervised"
    with runctx.use(DEBUGASSIST_MODE="autonomous"):
        assert runctx.get("DEBUGASSIST_MODE") == "autonomous"


def test_building_deps_no_longer_writes_the_environment() -> None:
    from pathlib import Path

    src = (Path(__file__).parents[2] / "pipeline" / "src" / "debugassist" / "pipeline").rglob("*.py")
    writes = [p.name for p in src if 'os.environ["' in p.read_text() and "] =" in p.read_text()]
    assert writes == []
