"""ROADMAP-100 051: one JSON event per line, with the run id inside a run, credentials masked."""

from __future__ import annotations

import json

from debugassist.core import logs, runctx


def test_events_are_json_lines_with_the_run_and_no_secrets() -> None:
    with runctx.use(DEBUGASSIST_RUN_ID="r1"):
        logs.event(
            "app", "error", error="push failed: https://x-access-token:ghs_abcdefghijklmnop@github.com"
        )
    logs.event("app", "count", runs_started=1)
    lines = [json.loads(line) for line in (logs.LOGS / "app.jsonl").read_text().splitlines()]
    assert [(e["event"], e.get("run_id")) for e in lines] == [("error", "r1"), ("count", None)]
    assert "ghs_abcdefghij" not in lines[0]["error"] and lines[1]["runs_started"] == 1
