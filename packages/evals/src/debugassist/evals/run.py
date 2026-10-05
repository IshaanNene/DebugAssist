"""`make eval` (SPEC §12): per catalog bug — reset → inject → simulate traffic → wait for discovery → run the
pipeline once per configuration and seed → score against ground truth → label the run's decisions.

GitHub, Jira and chat are forced to mock: evaluation runs never open real PRs or tickets. Each bug is
triggered once and every configuration/seed runs on the same discovered issue, so configurations are
compared on identical inputs. Results stream to evals/runs/<stamp>/results.jsonl as they finish.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from debugassist.core.ledger import Ledger
from debugassist.core.policy import ROOT
from debugassist.core.settings import get_settings
from debugassist.evals import labels, score
from debugassist.scenarios.catalog import Bug, get_bug, load_catalog

RUNS_OUT = ROOT / "evals" / "runs"
CLI = Path(sys.executable).parent / "debugassist"

CONFIGS: dict[str, dict[str, str]] = {
    "routed": {},  # the main configuration: each template's own Clef model
    "clef": {"DA_DECIDER": "clef"},
    "clef-flash": {"DA_DECIDER": "clef-flash"},
    "no-clef": {"DA_DECIDER": "llm"},  # the LLM decides everything, with self-reported confidence
    "no-d3": {"DA_ABLATE": "D3"},
    "no-d8": {"DA_ABLATE": "D8"},
    "no-d9": {"DA_ABLATE": "D9"},
    "no-d12": {"DA_ABLATE": "D12"},
    "no-d14": {"DA_ABLATE": "D14"},
}
MOCK_WRITES = {"DA_MODE_GITHUB": "mock", "DA_MODE_JIRA": "mock", "DA_MODE_CHAT": "mock"}


def trigger(bug: Bug, *, wipe: bool = True, log: Callable[[str], None] = print) -> list[str]:
    """Reset, inject and run the bug's scenario; returns the discovered issue refs, best source first."""
    from debugassist.scenarios import injector
    from debugassist.scenarios.environment import Environment
    from debugassist.simulator.scenarios import run_scenario

    env = Environment()
    if injector.current():
        injector.reset(env, wipe=wipe, log=log)
    elif wipe:
        injector.wipe_sources()
    injector.inject(bug, env, log=log)
    before_i = {i["id"] for i in env.vitals_issues()}
    before_r = {r["id"] for r in env.bugdrop_reports()}
    asyncio.run(run_scenario(bug.trigger.scenario, dict(bug.trigger.params), log=log, headless=True))
    time.sleep(3)  # SDK batches land
    issues = [i for i in env.vitals_issues() if i["id"] not in before_i]
    reports = [r["id"] for r in env.bugdrop_reports() if r["id"] not in before_r]

    def events(i: dict[str, Any]) -> int:
        return int(cast(dict[str, Any], i.get("group") or {}).get("count", 0))

    vitals = [i["id"] for i in sorted(issues, key=events, reverse=True)]
    order = {"vitals": vitals, "bugdrop": reports}
    return [ref for src in bug.discovery for ref in order.get(src, [])]


def run_pipeline(
    issue: str, config: str, seed: int, until: str | None, log: Callable[[str], None] = print
) -> str | None:
    env = {**os.environ, **MOCK_WRITES, **CONFIGS[config], "DA_LLM_SEED": str(seed)}
    args = [str(CLI), "run", issue, "--llm", "live"] + (["--until", until] if until else [])
    p = subprocess.run(args, env=env, capture_output=True, text=True, cwd=ROOT, timeout=5400)
    m = re.search(r"^run (\S+) \(", p.stdout, re.M)
    if not m:
        log(f"    ✗ no run started: {(p.stdout + p.stderr)[-400:]}")
        return None
    return m.group(1)


async def _clef_usd(ledger: Ledger, run_id: str) -> float:
    return sum(float(r.cost_usd) for r in await ledger.list(run_id=run_id))


async def evaluate(
    bug_ids: list[str],
    configs: list[str],
    seeds: int,
    *,
    until: str | None = "validate",
    hidden: bool = True,
    wipe: bool = True,
    log: Callable[[str], None] = print,
) -> Path:
    unknown = [c for c in configs if c not in CONFIGS]
    if unknown:
        raise ValueError(f"unknown configs {unknown}; known: {sorted(CONFIGS)}")
    out = RUNS_OUT / datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    (out / "plan.json").write_text(
        json.dumps({"bugs": bug_ids, "configs": configs, "seeds": seeds, "until": until}, indent=2)
    )
    ledger = await Ledger.open(get_settings().database_url)
    try:
        for bug_id in bug_ids:
            bug = get_bug(bug_id)
            log(f"{bug.id}: {bug.title}")
            refs = await asyncio.to_thread(trigger, bug, wipe=wipe, log=lambda m: log(f"  {m}"))
            if not refs:
                row = {"bug": bug.id, "error": "not discovered (no Vitals issue or BugDrop report)"}
                log(f"  ✗ {row['error']}")
                _append(out, row)
                continue
            issue = refs[0]
            log(f"  discovered {', '.join(refs)} → running on {issue}")
            for config in configs:
                for seed in range(1, seeds + 1):
                    t0 = time.time()
                    run_id = await asyncio.to_thread(run_pipeline, issue, config, seed, until, log)
                    if run_id is None:
                        _append(
                            out,
                            {
                                "bug": bug.id,
                                "issue": issue,
                                "config": config,
                                "seed": seed,
                                "error": "run did not start",
                            },
                        )
                        continue
                    labelled = await labels.label_run(ledger, run_id, bug)
                    result = await asyncio.to_thread(
                        score.score_run, run_id, bug, await _clef_usd(ledger, run_id), hidden
                    )
                    row = {
                        "config": config,
                        "seed": seed,
                        "issue": issue,
                        "labelled_decisions": labelled,
                        "wall_s": round(time.time() - t0, 1),
                        **result,
                    }
                    _append(out, row)
                    log(
                        f"    {config} seed {seed}: rca {row['rca']} · validated {row['validated']} · hidden {row['hidden_tests']} · ${row['usd']:.3f}"
                    )
    finally:
        await ledger.close()
    return out


def _append(out: Path, row: dict[str, Any]) -> None:
    with (out / "results.jsonl").open("a") as f:
        f.write(json.dumps(row, default=str) + "\n")


def catalog_ids() -> list[str]:
    return sorted(load_catalog())


def estimate(bug_ids: list[str], configs: list[str], seeds: int, per_run_usd: float) -> dict[str, Any]:
    n = len(bug_ids) * len(configs) * seeds
    return {"runs": n, "per_run_usd": round(per_run_usd, 3), "total_usd": round(n * per_run_usd, 2)}
