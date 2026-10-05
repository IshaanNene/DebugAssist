"""E1 — decision-only evaluation (PLAN §E1): re-ask every catalog-labelled decision from recorded runs,
with the exact state and questions the pipeline sent, to Clef, Clef-flash and the LLM decider, plus a
rules baseline; score each answer against the same catalog label. This isolates decision quality from the
rest of the pipeline and is cheap (one call per decision per backend)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from debugassist.core.policy import ROOT
from debugassist.core.settings import get_settings
from debugassist.decisions.engine import DecisionEngine, RunContext
from debugassist.decisions.factory import build_backend
from debugassist.decisions.templates import QUESTION_ADAPTER, load_templates
from debugassist.evals import labels
from debugassist.scenarios.catalog import Bug

OUT = ROOT / "evals" / "runs" / "e1"

# Rules baseline: the answer a fixed rule would give, per decision (what a team might hard-code).
RULES: dict[str, dict[str, Any]] = {
    "D01": {"chosen": {"priority": 2.0}, "action": None},  # everything is P2
    "D05": {"chosen": {"category": "own_code"}, "action": None},  # assume it's our bug
    "D11": {"chosen": {}, "action": "keep"},  # never roll back automatically
    "D12": {"chosen": {"location": "none"}, "action": "search_wider"},  # no localization
    "D14": {"chosen": {"tier": "unit"}, "action": "tier_unit"},  # always a unit test
    "D16": {"chosen": {"outcome": "draft_pr"}, "action": "draft_pr"},  # always a draft PR
}


def _questions(raw: dict[str, Any]) -> dict[str, Any]:
    return {k: QUESTION_ADAPTER.validate_python(v) for k, v in raw.items()}


async def replay(rows: list[Any], bugs: dict[str, Bug], backends: list[str]) -> list[dict[str, Any]]:
    """One result per (labelled row, backend)."""
    s = get_settings()
    templates = {t.id: t for t in load_templates().values()}
    engines: dict[str, tuple[DecisionEngine, Any]] = {}
    for b in backends:
        if b == "rules":
            continue
        backend = build_backend(s, "llm" if b == "llm" else "clef")
        engines[b] = (DecisionEngine(backend, ledger=None), "clef-flash" if b == "clef-flash" else "clef")
    out: list[dict[str, Any]] = []
    for r in rows:
        raw: Any = r.outcome_label
        label = cast(dict[str, Any], raw if isinstance(raw, dict) else json.loads(raw or "{}"))
        bug = bugs.get(str(label.get("bug")))
        t = templates.get(r.decision_id)
        if bug is None or t is None:
            continue
        names = {"names": labels.d12_names(dict(r.questions or {}))}
        base: dict[str, Any] = {
            "row": r.id,
            "run_id": r.run_id,
            "decision": r.decision_id,
            "bug": bug.id,
            "expected": label.get("expected"),
        }
        for b in backends:
            if b == "rules":
                rule = RULES.get(r.decision_id[:3])
                if rule is None:
                    continue
                v = labels.judge(r.decision_id, rule["chosen"], rule["action"], bug, names)
                out.append(
                    {
                        **base,
                        "backend": "rules",
                        "got": v and v["got"],
                        "correct": bool(v and v["correct"]),
                        "confidence": None,
                        "latency_ms": 0,
                        "cost_usd": 0.0,
                    }
                )
                continue
            engine, model = engines[b]
            try:
                run_ = engine._run  # pyright: ignore[reportPrivateUsage]
                d = await run_(
                    t, r.state, None, _questions(dict(r.questions)), RunContext(run_id="e1"), model
                )
            except Exception as exc:
                out.append({**base, "backend": b, "error": f"{type(exc).__name__}: {exc}"[:200]})
                continue
            v = labels.judge(r.decision_id, dict(d.chosen), d.action, bug, names)
            out.append(
                {
                    **base,
                    "backend": b,
                    "got": v and v["got"],
                    "correct": bool(v and v["correct"]),
                    "confidence": d.confidence,
                    "band": d.band.value if d.band else None,
                    "latency_ms": d.latency_ms,
                    "cost_usd": d.cost_usd,
                }
            )
    return out


def save(results: list[dict[str, Any]]) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{datetime.now(UTC):%Y%m%d-%H%M%S}.jsonl"
    path.write_text("".join(json.dumps(r, default=str) + "\n" for r in results))
    return path
