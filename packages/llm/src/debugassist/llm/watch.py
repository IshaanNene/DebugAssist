"""Live progress and stall conditions for agents.

Every model turn and tool call is reported as it happens (console via the `debugassist.progress`
logger, and one JSON line per event in `.data/runs/<run>/agents/<node>.jsonl`), so a run can be
followed while it works instead of only after it finishes. The watchdog also decides when an agent
should stop: wall clock exceeded, or the same tool call repeated after a warning.
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("debugassist.progress")


def _brief(args: dict[str, Any], n: int = 70) -> str:
    text = ", ".join(str(v).replace("\n", " ") for v in args.values())
    return text if len(text) <= n else text[: n - 1] + "…"


@dataclass
class Watchdog:
    node: str
    max_wall_s: float = 900
    repeat_warn: int = 3  # identical calls before the agent is told to move on
    repeat_stop: int = 5  # identical calls before the agent is stopped
    events_file: Path | None = None
    started: float = field(default_factory=time.monotonic)
    turn: int = 0
    stop_reason: str | None = None
    _seen: Counter[str] = field(default_factory=Counter[str])
    _turn_t0: float = 0.0

    def _emit(self, kind: str, line: str, **data: Any) -> None:
        log.info("    · %s %s", self.node, line)
        if self.events_file is not None:
            self.events_file.parent.mkdir(parents=True, exist_ok=True)
            rec = {
                "at": datetime.now(UTC).isoformat(),
                "node": self.node,
                "turn": self.turn,
                "kind": kind,
                **data,
            }
            with self.events_file.open("a") as f:
                f.write(json.dumps(rec, default=str) + "\n")

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def model_start(self) -> None:
        self.turn += 1
        self._turn_t0 = time.monotonic()

    def model_end(self, input_tokens: int, output_tokens: int, tool_calls: list[str], text: str) -> None:
        ms = int((time.monotonic() - self._turn_t0) * 1000)
        what = ", ".join(tool_calls) if tool_calls else (f"says: {text[:80]!r}" if text else "no tool call")
        self._emit(
            "model",
            f"t{self.turn} model {ms / 1000:.1f}s (in {input_tokens / 1000:.1f}k, out {output_tokens}) → {what}",
            ms=ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tool_calls=tool_calls,
        )

    def model_error(self, exc: Exception) -> None:
        ms = int((time.monotonic() - self._turn_t0) * 1000)
        self._emit(
            "model_error",
            f"t{self.turn} model failed after {ms / 1000:.1f}s: {type(exc).__name__}: {str(exc)[:120]}",
            ms=ms,
            error=str(exc)[:500],
        )

    def tool(self, name: str, args: dict[str, Any], ok: bool, ms: int, preview: str) -> str | None:
        """Record a tool call; returns a note to append to its result when the agent is repeating itself."""
        key = f"{name}:{json.dumps(args, sort_keys=True, default=str)}"
        self._seen[key] += 1
        n = self._seen[key]
        status = "ok" if ok else "failed"
        first = preview.strip().splitlines()[0][:70] if preview.strip() else ""
        self._emit(
            "tool",
            f"t{self.turn} ⚙ {name}({_brief(args)}) {status} {ms}ms  {first}",
            tool=name,
            args=args,
            ok=ok,
            ms=ms,
            repeat=n,
        )
        if n >= self.repeat_stop:
            self.stop(f"stalled: {name}({_brief(args, 40)}) repeated {n} times")
            return None
        if n >= self.repeat_warn:
            self._emit(
                "warn", f"⚠ {name}({_brief(args, 40)}) repeated {n}× — told the agent to move on", repeat=n
            )
            return (
                f"\n\n[watchdog] You have made this exact call {n} times; its result has not changed. Use what you "
                "already have and take the next step (edit, run the test, or submit_result). Repeating it again "
                "stops this step."
            )
        return None

    def stop(self, reason: str) -> None:
        if self.stop_reason is None:
            self.stop_reason = reason
            self._emit("stop", f"⛔ stopping: {reason}", reason=reason)

    def check(self) -> str | None:
        """Called before every model turn: the reason to stop now, if any."""
        if self.stop_reason is None and self.elapsed > self.max_wall_s:
            self.stop(f"timeout: {self.elapsed:.0f}s > {self.max_wall_s:.0f}s wall clock")
        return self.stop_reason

    def finish(self, status: str, turns: int, cost: float) -> None:
        self._emit(
            "done",
            f"done: {status} · {turns} turns · {self.elapsed:.0f}s · ${cost:.4f}",
            status=status,
            turns=turns,
            seconds=round(self.elapsed),
            cost_usd=cost,
        )
