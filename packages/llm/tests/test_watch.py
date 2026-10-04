from __future__ import annotations

import json
from pathlib import Path

from debugassist.llm.watch import Watchdog


def test_events_are_logged_live(tmp_path: Path) -> None:
    w = Watchdog(node="fix", events_file=tmp_path / "fix.jsonl")
    w.model_start()
    w.model_end(3200, 150, ["read_file"], "")
    assert w.tool("read_file", {"path": "src/a.ts"}, True, 3, "1  export const a = 1;") is None
    w.finish("ok", 1, 0.001)
    kinds = [json.loads(line)["kind"] for line in (tmp_path / "fix.jsonl").read_text().splitlines()]
    assert kinds == ["model", "tool", "done"]


def test_repeated_calls_warn_then_stop() -> None:
    w = Watchdog(node="reproduce", repeat_warn=3, repeat_stop=5)
    notes = [w.tool("read_file", {"path": "src/a.ts"}, True, 1, "x") for _ in range(5)]
    assert notes[:2] == [None, None]
    assert notes[2] and "[watchdog]" in notes[2] and "3 times" in notes[2]
    assert w.check() and w.stop_reason and w.stop_reason.startswith("stalled")
    other = Watchdog(node="fix")
    for i in range(6):  # different arguments are progress, not a loop
        assert other.tool("read_file", {"path": f"src/{i}.ts"}, True, 1, "x") is None
    assert other.check() is None


def test_wall_clock_limit() -> None:
    w = Watchdog(node="fix", max_wall_s=10)
    w.started -= 11
    assert w.check() and w.stop_reason and w.stop_reason.startswith("timeout")
