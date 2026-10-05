"""Decision quality from labelled ledger rows (SPEC §12): accuracy, Brier, ECE, selective accuracy at the
act threshold, latency, cost — per decision, and per backend/model so Clef, Clef-flash and the LLM decider
can be compared."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from statistics import median
from typing import Any, cast


@dataclass(frozen=True)
class Point:
    decision: str
    backend: str
    model: str
    confidence: float  # the policy question's probability (-1 = per item)
    correct: bool
    latency_ms: float
    cost_usd: float


def points(rows: Iterable[Any], source: str | None = None) -> list[Point]:
    out: list[Point] = []
    for r in rows:
        label: Any = r.outcome_label if not isinstance(r.outcome_label, str) else json.loads(r.outcome_label)
        if not isinstance(label, dict) or "correct" not in label:
            continue
        if source and getattr(r, "outcome_source", None) != source:
            continue
        out.append(
            Point(
                r.decision_id,
                r.backend,
                r.model,
                float(r.confidence),
                bool(cast(dict[str, Any], label)["correct"]),
                float(r.latency_ms),
                float(r.cost_usd),
            )
        )
    return out


def brier(ps: list[Point]) -> float | None:
    xs = [(p.confidence, p.correct) for p in ps if p.confidence >= 0]
    return round(sum((c - float(y)) ** 2 for c, y in xs) / len(xs), 4) if xs else None


def reliability(ps: list[Point], bins: int = 10) -> list[dict[str, float]]:
    """Per confidence bin: mean confidence, accuracy, count (for the reliability diagram and ECE)."""
    out: list[dict[str, float]] = []
    xs = [p for p in ps if p.confidence >= 0]
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        inb = [p for p in xs if lo <= p.confidence < hi or (b == bins - 1 and p.confidence == 1.0)]
        if inb:
            out.append(
                {
                    "lo": lo,
                    "hi": hi,
                    "confidence": sum(p.confidence for p in inb) / len(inb),
                    "accuracy": sum(p.correct for p in inb) / len(inb),
                    "n": len(inb),
                }
            )
    return out


def ece(ps: list[Point], bins: int = 10) -> float | None:
    xs = [p for p in ps if p.confidence >= 0]
    if not xs:
        return None
    return round(
        sum(b["n"] * abs(b["accuracy"] - b["confidence"]) for b in reliability(xs, bins)) / len(xs), 4
    )


def summarize(ps: list[Point], tau: float | None = None) -> dict[str, Any]:
    if not ps:
        return {"n": 0}
    lat = sorted(p.latency_ms for p in ps)
    acted = [p for p in ps if tau is not None and p.confidence >= tau]
    return {
        "n": len(ps),
        "accuracy": round(sum(p.correct for p in ps) / len(ps), 4),
        "brier": brier(ps),
        "ece": ece(ps),
        "coverage_at_tau": round(len(acted) / len(ps), 4) if tau is not None else None,
        "accuracy_at_tau": round(sum(p.correct for p in acted) / len(acted), 4) if acted else None,
        "latency_p50_ms": median(lat),
        "latency_p95_ms": lat[min(len(lat) - 1, int(0.95 * len(lat)))],
        "usd_per_1k": round(1000 * sum(p.cost_usd for p in ps) / len(ps), 4),
    }


def by_decision(ps: list[Point], taus: dict[str, float] | None = None) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[Point]] = {}
    for p in ps:
        groups.setdefault(p.decision, []).append(p)
    return {d: summarize(g, (taus or {}).get(d)) for d, g in sorted(groups.items())}
