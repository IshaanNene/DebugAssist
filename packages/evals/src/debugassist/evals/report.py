# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# (matplotlib's type stubs are partial; everything else here is typed.)
"""Evaluation report (SPEC §12): evals/reports/<date>/report.md + CSV + charts, generated only from result
files written by `debugassist eval run` / `eval replay` and from the decision ledger. README numbers come
from here and nowhere else."""

from __future__ import annotations

import csv
import json
import subprocess
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from debugassist.core.policy import ROOT
from debugassist.evals import metrics

REPORTS = ROOT / "evals" / "reports"


def load_results(dirs: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for d in dirs:
        f = d / "results.jsonl"
        if f.is_file():
            rows += [
                json.loads(line) | {"eval": d.name} for line in f.read_text().splitlines() if line.strip()
            ]
    return rows


def _rate(rows: list[dict[str, Any]], pred: Any) -> float | None:
    return round(sum(1 for r in rows if pred(r)) / len(rows), 3) if rows else None


def _ms(values: list[float]) -> str:
    if not values:
        return "–"
    return f"{mean(values):.3g} ± {pstdev(values):.2g}" if len(values) > 1 else f"{values[0]:.3g}"


def by_config(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per configuration: rates per seed, then mean ± std across seeds (the SPEC's ≥3 seeds)."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if "rca" in r:
            groups[r["config"]].append(r)
    out: list[dict[str, Any]] = []
    for config, rs in sorted(groups.items()):
        seeds: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for r in rs:
            seeds[int(r["seed"])].append(r)

        def per_seed(
            pred: Callable[[dict[str, Any]], bool], seeds: dict[int, list[dict[str, Any]]] = seeds
        ) -> list[float]:
            return [v for s in seeds.values() if (v := _rate(s, pred)) is not None]

        sims = [float(r["diff_similarity"]) for r in rs if r.get("diff_similarity") is not None]
        hidden = [r for r in rs if r.get("hidden_tests") is not None]
        out.append(
            {
                "config": config,
                "runs": len(rs),
                "bugs": len({r["bug"] for r in rs}),
                "seeds": len(seeds),
                "rca_exact": _ms(per_seed(lambda r: r["rca"] == "exact")),
                "rca_exact_or_directional": _ms(per_seed(lambda r: r["rca"] in ("exact", "directional"))),
                "category_ok": _ms(per_seed(lambda r: r["category_ok"])),
                "outcome_ok": _ms(per_seed(lambda r: r["outcome_ok"])),
                "validated": _ms(per_seed(lambda r: r["validated"])),
                "hidden_tests_pass": f"{sum(1 for r in hidden if r['hidden_tests'])}/{len(hidden)}"
                if hidden
                else "–",
                "diff_similarity": _ms(sims),
                "unsupported_claims": _ms([float(r["claims_unsupported"]) for r in rs]),
                "turns": _ms([float(r["turns"]) for r in rs]),
                "usd": _ms([float(r["usd"]) for r in rs]),
                "time_to_rca_s": _ms(
                    [float(r["discovery_to_rca_s"]) for r in rs if r.get("discovery_to_rca_s") is not None]
                ),
                "pipeline_s": _ms([float(r["pipeline_s"]) for r in rs if r.get("pipeline_s") is not None]),
            }
        )
    return out


def e1_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if "correct" in r:
            groups[(r["decision"], r["backend"])].append(r)
    out: list[dict[str, Any]] = []
    for (decision, backend), rs in sorted(groups.items()):
        conf = [r for r in rs if r.get("confidence") is not None and float(r["confidence"]) >= 0]
        pts = [
            metrics.Point(
                decision,
                backend,
                backend,
                float(r["confidence"]),
                bool(r["correct"]),
                float(r.get("latency_ms") or 0),
                float(r.get("cost_usd") or 0),
            )
            for r in conf
        ]
        out.append(
            {
                "decision": decision,
                "backend": backend,
                "n": len(rs),
                "accuracy": round(sum(r["correct"] for r in rs) / len(rs), 3),
                "brier": metrics.brier(pts),
                "ece": metrics.ece(pts),
                "latency_p50_ms": sorted(float(r.get("latency_ms") or 0) for r in rs)[len(rs) // 2],
                "usd_per_1k": round(1000 * sum(float(r.get("cost_usd") or 0) for r in rs) / len(rs), 4),
            }
        )
    return out


def _csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v) if isinstance(v, dict | list) else v) for k, v in r.items()})


def _md_table(rows: list[dict[str, Any]], cols: list[str]) -> str:
    if not rows:
        return "_no data_\n"
    head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    return head + "".join("| " + " | ".join(str(r.get(c, "–")) for c in cols) + " |\n" for r in rows)


def _chart_configs(rows: list[dict[str, Any]], path: Path) -> None:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if "rca" in r:
            groups[r["config"]].append(r)
    if not groups:
        return
    names = sorted(groups)
    exact = [sum(r["rca"] == "exact" for r in groups[n]) / len(groups[n]) for n in names]
    direc = [sum(r["rca"] == "directional" for r in groups[n]) / len(groups[n]) for n in names]
    fig, ax = plt.subplots(figsize=(max(4, 1.1 * len(names)), 3.2))
    ax.bar(names, exact, label="exact", color="#2a9d8f")
    ax.bar(names, direc, bottom=exact, label="directional", color="#e9c46a")
    ax.set_ylim(0, 1)
    ax.set_ylabel("share of runs")
    ax.set_title("RCA accuracy by configuration")
    ax.legend(frameon=False)
    plt.xticks(rotation=30, ha="right")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _chart_reliability(points: list[metrics.Point], path: Path) -> None:
    bins = metrics.reliability(points)
    if not bins:
        return
    fig, ax = plt.subplots(figsize=(3.6, 3.4))
    ax.plot([0, 1], [0, 1], "--", color="#999", lw=1)
    ax.plot([b["confidence"] for b in bins], [b["accuracy"] for b in bins], "o-", color="#e76f51")
    for b in bins:
        ax.annotate(
            str(int(b["n"])),
            (b["confidence"], b["accuracy"]),
            fontsize=7,
            xytext=(3, 3),
            textcoords="offset points",
        )
    ax.set_xlabel("Clef confidence")
    ax.set_ylabel("accuracy")
    ax.set_title("Reliability (labelled decisions)")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _chart_e1(e1: list[dict[str, Any]], path: Path) -> None:
    if not e1:
        return
    decisions = sorted({r["decision"] for r in e1})
    backends = sorted({r["backend"] for r in e1})
    fig, ax = plt.subplots(figsize=(max(4, 0.9 * len(decisions) * len(backends) / 2), 3.2))
    w = 0.8 / len(backends)
    for i, b in enumerate(backends):
        acc = [
            next((r["accuracy"] for r in e1 if r["decision"] == d and r["backend"] == b), 0)
            for d in decisions
        ]
        ax.bar([x + i * w for x in range(len(decisions))], acc, w, label=b)
    ax.set_xticks([x + 0.4 - w / 2 for x in range(len(decisions))], [d[:3] for d in decisions])
    ax.set_ylim(0, 1)
    ax.set_ylabel("accuracy")
    ax.set_title("Decision accuracy by decider (E1)")
    ax.legend(frameon=False, fontsize=7)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def write(
    eval_dirs: list[Path], e1_files: list[Path], ledger_points: list[metrics.Point], taus: dict[str, float]
) -> Path:
    stamp = datetime.now(UTC)
    out = REPORTS / stamp.strftime("%Y-%m-%d")
    out.mkdir(parents=True, exist_ok=True)
    rows = load_results(eval_dirs)
    e1_rows = [json.loads(line) for f in e1_files for line in f.read_text().splitlines() if line.strip()]
    cfg = by_config(rows)
    e1 = e1_summary(e1_rows)
    dec = [{"decision": d, **s} for d, s in metrics.by_decision(ledger_points, taus).items()]
    _csv(out / "results.csv", rows)
    _csv(out / "by_config.csv", cfg)
    _csv(out / "decisions.csv", dec)
    _csv(out / "e1.csv", e1)
    _chart_configs(rows, out / "rca_by_config.svg")
    _chart_reliability(ledger_points, out / "reliability.svg")
    _chart_e1(e1, out / "e1_accuracy.svg")
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    failures = [r for r in rows if "error" in r and "rca" not in r]
    per_bug = sorted(
        (
            {
                "bug": r["bug"],
                "config": r["config"],
                "seed": r["seed"],
                "rca": r["rca"],
                "location": r.get("rca_location"),
                "validated": r["validated"],
                "hidden": r.get("hidden_tests"),
                "usd": r["usd"],
            }
            for r in rows
            if "rca" in r
        ),
        key=lambda r: (r["bug"], r["config"], r["seed"]),
    )
    md = f"""# DebugAssist evaluation — {stamp:%Y-%m-%d}

Generated by `debugassist eval report` from {len(eval_dirs)} eval run(s) and {len(e1_files)} decision replay(s) at
commit `{sha}`. Every number below comes from files in `evals/runs/` and the decision ledger; nothing is hand-entered.

**Read with care:** {len({r["bug"] for r in rows if "rca" in r})} bug(s), {len([r for r in rows if "rca" in r])} pipeline run(s) in total. Small n: differences of one or two
runs between configurations are noise. "± x" is the standard deviation across seeds.

## Pipeline, by configuration

{_md_table(cfg, ["config", "runs", "bugs", "seeds", "rca_exact", "rca_exact_or_directional", "category_ok", "outcome_ok", "validated", "hidden_tests_pass", "diff_similarity", "unsupported_claims", "turns", "usd", "time_to_rca_s"])}
![RCA accuracy by configuration](rca_by_config.svg)

Definitions: **exact** = file and function match ground truth; **directional** = right file or module; for
"not our bug" cases, exact = routed with the right category and no fix attempted. **hidden tests** = the
catalog's hidden tests pass on the agent's change (run by the evaluator in a copy of the worktree).

## Decisions (labelled from the catalog)

{_md_table(dec, ["decision", "n", "accuracy", "brier", "ece", "coverage_at_tau", "accuracy_at_tau", "latency_p50_ms", "usd_per_1k"])}
![Reliability](reliability.svg)

## Decision replay (E1): Clef vs Clef-flash vs LLM decider vs rules

{_md_table(e1, ["decision", "backend", "n", "accuracy", "brier", "ece", "latency_p50_ms", "usd_per_1k"])}
![E1](e1_accuracy.svg)

## Runs

{_md_table(per_bug, ["bug", "config", "seed", "rca", "location", "validated", "hidden", "usd"])}
{"## Failures" + chr(10) + chr(10) + _md_table(failures, ["bug", "config", "seed", "error"]) if failures else ""}
## Reproduce

```
debugassist eval run --bugs <ids> --configs <names> --seeds <n>
debugassist eval replay
debugassist eval report
```
"""
    (out / "report.md").write_text(md)
    return out
