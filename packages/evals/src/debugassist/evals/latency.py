"""Where a run's time goes (ROADMAP-100 041): p50 / p95 / max per pipeline node from stored runs' `timings_ms`."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, cast

from debugassist.pipeline.state import NODE_KIND


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile (no interpolation: with tens of runs it reports a value that happened)."""
    ordered = sorted(values)
    rank = max(1, min(len(ordered), round(q / 100 * len(ordered) + 0.5)))
    return ordered[rank - 1]


def profile(state_files: list[Path]) -> list[dict[str, Any]]:
    """One row per node in plan order, then a `run` row for whole runs; seconds."""
    per_node: dict[str, list[float]] = defaultdict(list)
    totals: list[float] = []
    for f in state_files:
        try:
            timings: dict[str, int] = json.loads(f.read_text()).get("timings_ms") or {}
        except (OSError, json.JSONDecodeError):
            continue  # a run being written, or an old file: skip it, never fail the profile
        for node, ms in timings.items():
            per_node[node].append(ms / 1000)
        if timings:
            totals.append(sum(timings.values()) / 1000)
    order = [n for n in NODE_KIND if n in per_node] + sorted(set(per_node) - set(NODE_KIND))
    rows = [_row(n, per_node[n]) for n in order]
    return [*rows, _row("run", totals)] if totals else rows


def _row(name: str, values: list[float]) -> dict[str, Any]:
    return {
        "node": name,
        "runs": len(values),
        "p50_s": round(percentile(values, 50), 1),
        "p95_s": round(percentile(values, 95), 1),
        "max_s": round(max(values), 1),
    }


SANDBOX_TOOLS = {"run_command", "run_e2e"}
WORKSPACE_TOOLS = {"list_dir", "read_file", "grep", "outline_file", "edit_file", "write_file", "read_log",
                   "submit_result"}  # fmt: skip


def time_split(state: dict[str, Any]) -> dict[str, float | None]:
    """Seconds an agent spent in the model, the sandbox, MCP tools and its own file tools, over every agent of a
    run (ROADMAP-100 042). Model time is each agent's wall time minus its tool time; None when the run predates
    wall-time recording."""
    agents: list[dict[str, Any]] = []

    def walk(v: Any) -> None:
        if isinstance(v, dict):
            d = cast(dict[str, Any], v)
            if "tool_calls" in d and "turns" in d:
                agents.append(d)
            for x in d.values():
                walk(x)
        elif isinstance(v, list):
            for x in cast(list[Any], v):
                walk(x)

    walk(state)
    split: dict[str, float] = {"sandbox_s": 0.0, "mcp_s": 0.0, "workspace_s": 0.0}
    model: float | None = 0.0 if agents else None
    for a in agents:
        tool_ms = 0.0
        for c in cast(list[dict[str, Any]], a.get("tool_calls") or []):
            ms = float(c.get("ms") or 0)
            tool_ms += ms
            name = str(c.get("name", ""))
            key = (
                "sandbox_s"
                if name in SANDBOX_TOOLS
                else "workspace_s"
                if name in WORKSPACE_TOOLS
                else "mcp_s"
            )
            split[key] += ms / 1000
        wall = a.get("wall_ms")
        model = None if model is None or wall is None else model + max(0.0, float(wall) - tool_ms) / 1000
    return {
        "model_s": None if model is None else round(model, 1),
        **{k: round(v, 1) for k, v in split.items()},
    }
