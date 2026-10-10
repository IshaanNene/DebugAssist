"""Eval runs as Langfuse experiments (ROADMAP P16), following Langfuse v4's OpenTelemetry experiment format.

Each `evals/runs/<stamp>` sweep becomes one experiment per (config, arm); each scored run becomes one experiment
item: a root span carrying the item's input (the issue the agent got), its output (what the agent concluded and
did), the expected output from the catalog, and scores for root cause, category, validation, hidden tests, cost
and turns. Experiments are compared side by side in Langfuse's UI.

Ids are deterministic (from the run id), so exporting again updates the same traces and scores instead of
duplicating them. The answer key goes only to Langfuse, an evaluation store no agent reads; it never enters a
sandbox or a prompt.

Format: https://langfuse.com/integrations/native/opentelemetry/experiments (verified 2026-10-10, Langfuse 4.56).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from debugassist.core import tracing

DATASET = "debugassist-catalog"
RCA_VALUE = {"exact": 1.0, "directional": 0.5, "wrong": 0.0}


def _hex(seed: str, n: int) -> int:
    return int(hashlib.sha256(seed.encode()).hexdigest()[: n * 2], 16)


def trace_id(run_id: str) -> int:
    return _hex(f"debugassist-experiment-trace:{run_id}", 16)


def span_id(run_id: str) -> int:
    return _hex(f"debugassist-experiment-root:{run_id}", 8)


def _bool(v: Any) -> bool | None:
    if v in (True, "True", "true"):
        return True
    if v in (False, "False", "false"):
        return False
    return None


def experiment_of(row: dict[str, Any], stamp: str) -> tuple[str, str]:
    """(id, name): one experiment per sweep and configuration/arm."""
    config, arm = row.get("config", ""), row.get("arm") or ""
    label = config if arm in ("", config) else f"{config} · {arm}"
    return f"{stamp}-{row.get('arm') or row.get('config', '')}", f"{label} · {stamp}"


def run_start(run_id: str) -> datetime:
    """Run ids start with their UTC start time: 20261010-093546-vit-1001."""
    return datetime.strptime(run_id[:15], "%Y%m%d-%H%M%S").replace(tzinfo=UTC)


def item(row: dict[str, Any], expected: dict[str, Any] | None) -> dict[str, Any]:
    """Input, output, expected output and scores for one scored run."""
    out: dict[str, Any] = {
        "input": {
            "bug": row["bug"],
            "issue": row.get("issue"),
            "agent_type": row.get("agent_type"),
            "config": row.get("config"),
        },
        "output": {
            "rca_location": row.get("rca_location"),
            "outcome": row.get("outcome") or row.get("status"),
            "validated": _bool(row.get("validated")),
            "hidden_tests": _bool(row.get("hidden_tests")),
            "tier": row.get("tier"),
        },
        "expected": expected,
        "metadata": {k: row.get(k) for k in ("run_id", "arm", "commit", "model", "seed") if row.get(k)},
    }
    scores: list[tuple[str, float, str]] = []
    if row.get("rca") in RCA_VALUE:
        scores.append(("rca", RCA_VALUE[row["rca"]], "NUMERIC"))
    for name in ("category_ok", "validated", "hidden_tests"):
        b = _bool(row.get(name))
        if b is not None:
            scores.append((name, 1.0 if b else 0.0, "BOOLEAN"))
    for name in ("usd", "turns"):
        if row.get(name) not in (None, ""):
            scores.append((name, float(row[name]), "NUMERIC"))
    out["scores"] = scores
    return out


def expected_for(bug_id: str) -> dict[str, Any] | None:
    from debugassist.scenarios.catalog import load_catalog

    bug = load_catalog().get(bug_id)
    if bug is None:
        return None
    loc = bug.ground_truth.location
    return {
        "category": str(bug.category),
        "expected_outcome": str(bug.expected_outcome),
        "location": "/".join(p for p in (loc.repo, loc.file) if p)
        + (f" → {loc.function}" if loc.function else ""),
    }


def export(
    dirs: list[Path],
    *,
    exporter: Any = None,
    post: Callable[[str, dict[str, Any]], None] | None = None,
    expected: Callable[[str], dict[str, Any] | None] = expected_for,
) -> dict[str, Any]:
    """Send every non-excluded run in `dirs` to Langfuse. `exporter`/`post` are injectable for tests."""
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.id_generator import IdGenerator

    if exporter is None or post is None:
        headers = tracing.langfuse_headers()
        if headers is None:
            raise RuntimeError(
                "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are required (see `make langfuse`)"
            )
        exporter = exporter or tracing.langfuse_exporter()

        def _post(path: str, body: dict[str, Any]) -> None:
            httpx.post(
                f"{tracing.langfuse_url()}{path}", headers=headers, json=body, timeout=10
            ).raise_for_status()

        post = post or _post

    class Fixed(IdGenerator):
        """Deterministic ids, so a re-export updates the same trace and root observation."""

        run_id = ""

        def generate_trace_id(self) -> int:
            return trace_id(self.run_id)

        def generate_span_id(self) -> int:
            return span_id(self.run_id)

    ids = Fixed()
    provider = TracerProvider(
        resource=Resource.create({"service.name": "debugassist-evals", "langfuse.environment": "experiment"}),
        id_generator=ids,
    )
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("debugassist.evals")

    sent: list[dict[str, Any]] = []
    for d in dirs:
        stamp = d.name
        for line in (d / "results.jsonl").read_text().splitlines():
            row = json.loads(line)
            if not row.get("run_id") or row.get("excluded") or not row.get("rca"):
                continue
            exp_id, exp_name = experiment_of(row, stamp)
            it = item(row, expected(row["bug"]))
            ids.run_id = row["run_id"]
            start = run_start(row["run_id"])
            end_ns = int((start.timestamp() + float(row.get("wall_s") or 0)) * 1e9)
            attrs: dict[str, Any] = {
                "langfuse.trace.name": f"{row['bug']} · {exp_name}",
                "langfuse.observation.type": "agent",
                "langfuse.environment": "experiment",
                "langfuse.experiment.id": exp_id,
                "langfuse.experiment.name": exp_name,
                "langfuse.experiment.dataset.id": DATASET,
                "langfuse.experiment.item.id": row["bug"],
                "langfuse.experiment.item.root_observation_id": format(span_id(row["run_id"]), "016x"),
                "langfuse.observation.input": json.dumps(it["input"]),
                "langfuse.observation.output": json.dumps(it["output"]),
                "session.id": row["run_id"],
                **{f"langfuse.trace.metadata.{k}": str(v) for k, v in it["metadata"].items()},
            }
            if it["expected"] is not None:
                attrs["langfuse.experiment.item.expected_output"] = json.dumps(it["expected"])
            span = tracer.start_span(
                "experiment-item", start_time=int(start.timestamp() * 1e9), attributes=attrs
            )
            span.end(end_time=end_ns)
            tid, sid = format(trace_id(row["run_id"]), "032x"), format(span_id(row["run_id"]), "016x")
            for name, value, kind in it["scores"]:
                post(
                    "/api/public/scores",
                    {
                        "id": f"{row['run_id']}-{name}",  # idempotent: re-export overwrites
                        "traceId": tid,
                        "observationId": sid,
                        "name": name,
                        "value": value,
                        "dataType": kind,
                    },
                )
            sent.append({"run_id": row["run_id"], "bug": row["bug"], "experiment": exp_name, "trace_id": tid})
    provider.force_flush()
    provider.shutdown()
    return {"items": len(sent), "experiments": sorted({s["experiment"] for s in sent}), "runs": sent}
