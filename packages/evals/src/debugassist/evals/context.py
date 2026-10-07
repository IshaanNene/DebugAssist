"""Where an agent's input tokens go (P15 prompt anatomy audit), from the per-turn agent logs.

Every model call re-sends the fixed prefix (system prompt, tool schemas, the task) plus the whole history.
Turn t+1's input minus turn t's input is what turn t added: the model's own message and its tool results. A
result added at turn t is then re-sent on every later turn, so its real cost is size × later turns. Splitting a
run's total input that way shows which technique would pay off: a big prefix → caching/skills; big re-sent tool
results → offloading, clearing, concise responses or programmatic tool calling.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from debugassist.evals.score import RUNS

CASSETTES = RUNS.parent / "cassettes"


@dataclass
class Anatomy:
    node: str
    turns: int = 0
    input_tokens: int = 0
    cached_tokens: int = 0
    prefix: int = 0  # turn-1 input: system prompt + tool schemas + task
    prefix_total: int = 0  # prefix × turns
    model_total: int = 0  # the model's own messages, re-sent
    tools_total: dict[str, int] = field(default_factory=dict[str, int])  # tool results, re-sent, per tool
    tools_added: dict[str, int] = field(default_factory=dict[str, int])  # tool result tokens when first added


def _events(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _weights(run_id: str, node: str) -> list[dict[str, int]]:
    """Per turn: the share of each tool in that turn's results, from the recorded transcript (by length)."""
    f = CASSETTES / run_id / f"{node}.json"
    if not f.is_file():
        return []
    msgs: list[dict[str, Any]] = json.loads(f.read_text()).get("transcript", [])
    turns: list[dict[str, int]] = []
    pending: list[str] = []
    for m in msgs:
        if m.get("type") == "ai":
            turns.append({})
            calls = cast(list[dict[str, Any]], m.get("tool_calls") or [])
            pending = [str(tc.get("name")) for tc in calls]
        elif m.get("type") == "tool" and turns:
            # tool messages follow their AI message in call order (the transcript keeps no names on them)
            name = pending.pop(0) if pending else "tool"
            turns[-1][name] = turns[-1].get(name, 0) + len(str(m.get("content", "")))
    return turns


def _segments(ev: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """One node log can hold several agent runs (fix attempts, one reproduce agent per tier): split at `done`."""
    segs: list[list[dict[str, Any]]] = [[]]
    for e in ev:
        segs[-1].append(e)
        if e.get("kind") == "done":
            segs.append([])
    return [s for s in segs if any(e.get("kind") == "model" for e in s)]


def anatomy(run_id: str, node_log: Path) -> Anatomy | None:
    segs = _segments(_events(node_log))
    if not segs:
        return None
    a = Anatomy(node=node_log.stem)
    shares_last = _weights(run_id, a.node)  # the recorded transcript is the node's last agent run
    for si, seg in enumerate(segs):
        models = [e for e in seg if e.get("kind") == "model"]
        tools_by_turn: dict[int, list[str]] = defaultdict(list)
        for e in seg:
            if e.get("kind") == "tool":
                tools_by_turn[int(e.get("turn", 0))].append(str(e.get("tool")))
        shares = shares_last if si == len(segs) - 1 else []
        a.turns += len(models)
        a.input_tokens += sum(int(e.get("input_tokens", 0)) for e in models)
        a.cached_tokens += sum(int(e.get("cached_tokens", 0)) for e in models)
        first = int(models[0].get("input_tokens", 0))
        a.prefix = max(a.prefix, first)
        a.prefix_total += first * len(models)
        for i in range(len(models) - 1):
            added = max(0, int(models[i + 1].get("input_tokens", 0)) - int(models[i].get("input_tokens", 0)))
            later = len(models) - (i + 1)  # model calls that re-send what turn i added
            own = min(added, int(models[i].get("output_tokens", 0)))  # includes reasoning: an upper bound
            rest = added - own
            a.model_total += own * later
            names = tools_by_turn.get(int(models[i].get("turn", i + 1))) or models[i].get("tool_calls") or []
            if not names or rest <= 0:
                a.model_total += rest * later
                continue
            w = shares[i] if i < len(shares) and shares[i] else {n: names.count(n) for n in set(names)}
            total_w = sum(w.values()) or 1
            for name, wt in w.items():
                part = round(rest * wt / total_w)
                a.tools_total[name] = a.tools_total.get(name, 0) + part * later
                a.tools_added[name] = a.tools_added.get(name, 0) + part
    return a


def audit(run_ids: list[str]) -> list[Anatomy]:
    out: list[Anatomy] = []
    for rid in run_ids:
        for log in sorted((RUNS / rid / "agents").glob("*.jsonl")):
            if a := anatomy(rid, log):
                out.append(a)
    return out


def summarize(items: list[Anatomy]) -> dict[str, Any]:
    total = sum(a.input_tokens for a in items) or 1
    prefix = sum(a.prefix_total for a in items)
    model = sum(a.model_total for a in items)
    tools: dict[str, int] = defaultdict(int)
    added: dict[str, int] = defaultdict(int)
    for a in items:
        for k, v in a.tools_total.items():
            tools[k] += v
        for k, v in a.tools_added.items():
            added[k] += v
    by_node: dict[str, list[Anatomy]] = defaultdict(list)
    for a in items:
        by_node[a.node.removeprefix("subagent_") if a.node.startswith("subagent_") else a.node].append(a)
    nodes = [
        {
            "node": n,
            "agents": len(xs),
            "turns_avg": round(sum(x.turns for x in xs) / len(xs), 1),
            "input_tokens": sum(x.input_tokens for x in xs),
            "share": round(sum(x.input_tokens for x in xs) / total, 3),
            "prefix_avg": round(sum(x.prefix for x in xs) / len(xs)),
            "cache_rate": round(
                sum(x.cached_tokens for x in xs) / max(1, sum(x.input_tokens for x in xs)), 3
            ),
        }
        for n, xs in sorted(by_node.items(), key=lambda kv: -sum(x.input_tokens for x in kv[1]))
    ]
    top_tools = sorted(tools.items(), key=lambda kv: -kv[1])
    return {
        "input_tokens": total,
        "cached_tokens": sum(a.cached_tokens for a in items),
        "prefix_share": round(prefix / total, 3),
        "model_share": round(model / total, 3),
        "tools_share": round(sum(tools.values()) / total, 3),
        "nodes": nodes,
        "tools": [
            {
                "tool": k,
                "resent_tokens": v,
                "share": round(v / total, 3),
                "added_tokens": added[k],
                "resend_factor": round(v / max(1, added[k]), 1),
            }
            for k, v in top_tools
        ],
    }


def report(summary: dict[str, Any], runs: int) -> str:
    def table(rows: list[dict[str, Any]], cols: list[str]) -> str:
        head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
        return head + "".join("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |\n" for r in rows)

    s = summary
    return f"""# Context audit

Generated by `debugassist eval context` from the per-turn agent logs of {runs} run(s): where input tokens go.
"Re-sent" counts a token once for every model call that carried it.

| | share of all input tokens |
|---|---|
| fixed prefix (system prompt, tool schemas, task) × turns | {s["prefix_share"]} |
| tool results, re-sent | {s["tools_share"]} |
| the model's own messages, re-sent | {s["model_share"]} |
| served from the prompt cache | {round(s["cached_tokens"] / s["input_tokens"], 3)} |

Total input: {s["input_tokens"]:,} tokens.

## By agent

{table(s["nodes"], ["node", "agents", "turns_avg", "input_tokens", "share", "prefix_avg", "cache_rate"])}
## By tool (results re-sent)

{table(s["tools"][:20], ["tool", "added_tokens", "resend_factor", "resent_tokens", "share"])}
"""
