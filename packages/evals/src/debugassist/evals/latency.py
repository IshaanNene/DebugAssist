"""Where a run's time goes (ROADMAP-100 041): p50 / p95 / max per pipeline node from stored runs' `timings_ms`."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

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
