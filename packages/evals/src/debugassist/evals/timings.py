"""Per-step timings of the runs a report covers, for the site's run replays (docs/SITE-REDESIGN.md).

Every executed pipeline step is a node file in the run store (`.data/runs/<id>/nodes/NN-<node>.json`, with its
`kind` and `ms`), so a step that ran twice is listed twice — `state.json`'s `timings_ms` keeps only the last. Steps
run one after another: each starts where the previous one ended. The site reads only generated reports, so this
export is how the store's timings reach it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel

from debugassist.pipeline.state import NODE_KIND


class Step(BaseModel):
    node: str
    kind: str  # NODE_KIND: deterministic, llm, deterministic+clef, llm+clef, clef
    start_ms: int
    ms: int


class RunTimings(BaseModel):
    run_id: str
    steps: list[Step]
    steps_ms: int  # the steps' sum; a run's wall time also counts the time between them


def _order(f: Path) -> tuple[int, str]:
    head = f.name.split("-", 1)[0]
    return (int(head) if head.isdigit() else 1 << 30, f.name)


def run_timings(run_dir: Path) -> RunTimings | None:
    """The run's steps in execution order, or None when the store has no complete node files for it."""
    steps: list[Step] = []
    t = 0
    for f in sorted((run_dir / "nodes").glob("*.json"), key=_order):
        try:
            rec = cast(dict[str, Any], json.loads(f.read_text()))
        except (OSError, json.JSONDecodeError):
            return None  # a run being written: leave it out rather than export half of it
        node = str(rec.get("node") or f.stem.split("-", 1)[-1])
        ms = int(rec.get("ms") or 0)
        kind = str(rec.get("kind") or NODE_KIND.get(node, "deterministic"))
        steps.append(Step(node=node, kind=kind, start_ms=t, ms=ms))
        t += ms
    return RunTimings(run_id=run_dir.name, steps=steps, steps_ms=t) if steps else None


def export(run_ids: list[str], runs_dir: Path) -> dict[str, Any]:
    """`runs`: the timings of every listed run the store has; `missing`: the ids it has no node files for."""
    found: list[RunTimings] = []
    missing: list[str] = []
    for rid in dict.fromkeys(run_ids):  # unique, in report order
        t = run_timings(runs_dir / rid)
        if t is None:
            missing.append(rid)
        else:
            found.append(t)
    return {"runs": [r.model_dump() for r in found], "missing": missing}
