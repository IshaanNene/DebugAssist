"""Read models over what runs leave behind: `.data/runs/<id>/` (state, node updates, agent logs), the
decision ledger, the chat inbox, deploys and feedback. Pure functions over files, so tests point them at
a temporary directory."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from statistics import median
from typing import Any, cast

import yaml

from debugassist.core.policy import ROOT
from debugassist.decisions.templates import Template, load_templates
from debugassist.pipeline.state import NODE_KIND


def obj(value: Any) -> dict[str, Any]:
    """A JSON object from run state or an API, or {} (keeps pyright strict over raw JSON)."""
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def arr(value: Any) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


@dataclass(frozen=True)
class Paths:
    data: Path = ROOT / ".data"
    root: Path = ROOT

    @property
    def runs(self) -> Path:
        return self.data / "runs"

    @property
    def ledger(self) -> Path:
        return self.data / "debugassist.db"

    @property
    def inbox(self) -> Path:
        return self.data / "mock" / "chat" / "inbox.jsonl"

    @property
    def feedback(self) -> Path:
        return self.data / "feedback.jsonl"


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a line being written right now
    return out


def run_ids(p: Paths) -> list[str]:
    if not p.runs.is_dir():
        return []
    return sorted((d.name for d in p.runs.iterdir() if (d / "state.json").is_file()), reverse=True)


def load_state(p: Paths, run_id: str) -> dict[str, Any] | None:
    f = p.runs / run_id / "state.json"
    if "/" in run_id or ".." in run_id or not f.is_file():
        return None
    return json.loads(f.read_text())


def started_at(run_id: str) -> str | None:
    try:
        return datetime.strptime(run_id[:15], "%Y%m%d-%H%M%S").replace(tzinfo=UTC).isoformat()
    except ValueError:
        return None


def summary(s: dict[str, Any]) -> dict[str, Any]:
    issue = obj(s.get("issue"))
    tr = obj(s.get("triage"))
    rca = obj(s.get("rca"))
    out = obj(rca.get("output"))
    v = obj(s.get("validation"))
    attempts = arr(s.get("fix_attempts"))
    return {
        "run_id": s["run_id"],
        "issue_ref": s.get("issue_ref"),
        "issue_id": issue.get("id") or s.get("issue_ref"),
        "source": issue.get("source"),
        "title": issue.get("title"),
        "app": issue.get("app"),
        "version": issue.get("last_version"),
        "status": s.get("status"),
        "llm_mode": s.get("llm_mode"),
        "started_at": started_at(s["run_id"]),
        "priority": tr.get("priority"),
        "severity": tr.get("severity"),
        "owner": tr.get("owner_team"),
        "oncall": tr.get("oncall"),
        "customer_impacting": tr.get("customer_impacting"),
        "worth_agent_run": tr.get("worth_agent_run"),
        "jira": tr.get("jira_key"),
        "category": out.get("category"),
        "location": f"{out['location']['file']} → {out['location']['function']}"
        if out.get("location")
        else None,
        "validated": bool(v.get("passed")),
        "tier": attempts[-1].get("tier") if attempts else None,
        "outcome": obj(s.get("ship")).get("outcome"),
        "pr": obj(s.get("pr")).get("url"),
        "watch": obj(s.get("watch")).get("status"),
        "cost_usd": round(sum(obj(s.get("costs")).values()), 4),
        "seconds": round(sum(obj(s.get("timings_ms")).values()) / 1000, 1),
    }


def runs(p: Paths, issue: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rid in run_ids(p):
        s = load_state(p, rid)
        if s is None:
            continue
        row = summary(s)
        if issue and issue not in (row["issue_id"], row["issue_ref"]):
            continue
        out.append(row)
        if len(out) >= limit:
            break
    return out


def graph(p: Paths, s: dict[str, Any]) -> list[dict[str, Any]]:
    """The fixed plan with each node's status: done / failed / running / pending / skipped."""
    rid = s["run_id"]
    timings: dict[str, int] = obj(s.get("timings_ms"))
    ran = [f.stem.split("-", 1)[1] for f in sorted((p.runs / rid / "nodes").glob("*.json"))]
    status = s.get("status")
    failed_at = next((e.split(":", 1)[0] for e in arr(s.get("errors")) if ":" in e), None)
    nodes: list[dict[str, Any]] = []
    for name, kind in NODE_KIND.items():
        runs_of = ran.count(name)
        if name == failed_at and status == "failed":
            st = "failed"
        elif runs_of:
            st = "done"
        elif (
            status == "running"
            and ran
            and list(NODE_KIND).index(name) == max(list(NODE_KIND).index(r) for r in ran) + 1
        ):
            st = "running"
        elif status in ("running",):
            st = "pending"
        else:
            st = "skipped"
        nodes.append({"id": name, "kind": kind, "status": st, "ms": timings.get(name), "runs": runs_of})
    return nodes


def calls(p: Paths, run_id: str) -> list[dict[str, Any]]:
    """Every model turn and tool call of every agent in the run, in time order."""
    d = p.runs / run_id / "agents"
    rows = [r for f in sorted(d.glob("*.jsonl")) for r in _jsonl(f)] if d.is_dir() else []
    return sorted(rows, key=lambda r: str(r.get("at", "")))


@cache
def templates() -> dict[str, Template]:
    return {t.id: t for t in load_templates().values()}


def _connect(p: Paths) -> sqlite3.Connection | None:
    if not p.ledger.is_file():
        return None
    con = sqlite3.connect(f"file:{p.ledger}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


LEDGER_QUERY = (
    "SELECT id, created_at, run_id, issue_id, parent_id, decision_id, backend, model, mode, questions,"
    " answers, chosen, confidence, band, action, latency_ms, input_tokens, output_tokens, cost_usd,"
    " n_calls, fallback_reason, outcome_label"
    " FROM decision_ledger WHERE run_id = ? ORDER BY created_at"
)


def _decision(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    for k in ("questions", "answers", "chosen", "outcome_label"):
        if isinstance(d.get(k), str):
            d[k] = json.loads(d[k])
    t = templates().get(d["decision_id"])
    if t is not None:
        d["description"] = t.description
        d["policy"] = {
            "question": t.policy.question,
            "tau_high": t.policy.tau_high,
            "tau_low": t.policy.tau_low,
        }
    return d


def decisions(p: Paths, run_id: str) -> list[dict[str, Any]]:
    con = _connect(p)
    if con is None:
        return []
    with con:
        rows = con.execute(
            LEDGER_QUERY,
            (run_id,),
        ).fetchall()
    return [_decision(r) for r in rows]


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, int(q * len(s)))]


def decision_quality(p: Paths) -> list[dict[str, Any]]:
    """Per decision: volume, backends, latency, cost, bands; accuracy and Brier once outcomes are labelled."""
    con = _connect(p)
    if con is None:
        return []
    with con:
        rows = con.execute(
            "SELECT decision_id, backend, mode, confidence, band, latency_ms, cost_usd, outcome_label FROM decision_ledger"
        ).fetchall()
    by: dict[str, list[sqlite3.Row]] = {}
    for r in rows:
        by.setdefault(r["decision_id"], []).append(r)
    out: list[dict[str, Any]] = []
    for did in sorted(by):
        rs = by[did]
        lat = [float(r["latency_ms"]) for r in rs]
        labelled = [r for r in rs if r["outcome_label"]]
        brier = acc = None
        if labelled:
            pairs = [
                (float(r["confidence"]), json.loads(r["outcome_label"]).get("correct")) for r in labelled
            ]
            pairs = [(c, bool(y)) for c, y in pairs if y is not None and c >= 0]
            if pairs:
                brier = round(sum((c - y) ** 2 for c, y in pairs) / len(pairs), 4)
                acc = round(sum(y for _, y in pairs) / len(pairs), 4)
        t = templates().get(did)
        out.append(
            {
                "decision_id": did,
                "description": t.description if t else None,
                "model": t.model if t else None,
                "n": len(rs),
                "backends": dict(sorted(_count(r["backend"] for r in rs).items())),
                "bands": dict(sorted(_count(r["band"] for r in rs).items())),
                "latency_p50": _pct(lat, 0.5),
                "latency_p95": _pct(lat, 0.95),
                "usd_per_1k": round(1000 * sum(float(r["cost_usd"]) for r in rs) / len(rs), 4),
                "labelled": len(labelled),
                "accuracy": acc,
                "brier": brier,
            }
        )
    return out


def _count(values: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        out[str(v)] = out.get(str(v), 0) + 1
    return out


def impact(p: Paths) -> dict[str, Any]:
    """Pipeline outcomes from the runs on disk (live and mock runs counted separately)."""
    states = [s for rid in run_ids(p) if (s := load_state(p, rid))]
    by_mode: dict[str, Any] = {}
    for mode in sorted({str(s.get("llm_mode")) for s in states}):
        ss = [s for s in states if str(s.get("llm_mode")) == mode]
        rca_s = [
            sum(v for k, v in obj(s.get("timings_ms")).items() if k in list(NODE_KIND)[:4]) / 1000
            for s in ss
            if obj(s.get("rca")).get("output")
        ]
        pr_s = [sum(obj(s.get("timings_ms")).values()) / 1000 for s in ss if s.get("pr")]
        costs = [sum(obj(s.get("costs")).values()) for s in ss if obj(s.get("rca")).get("output")]
        by_mode[mode] = {
            "runs": len(ss),
            "outcomes": _count(obj(s.get("ship")).get("outcome") or s.get("status") for s in ss),
            "rca_produced": len(rca_s),
            "validated_fixes": sum(1 for s in ss if obj(s.get("validation")).get("passed")),
            "prs": len(pr_s),
            "resolved_after_deploy": sum(1 for s in ss if obj(s.get("watch")).get("status") == "resolved"),
            "time_to_rca_s_median": round(median(rca_s), 1) if rca_s else None,
            "time_to_pr_s_median": round(median(pr_s), 1) if pr_s else None,
            "cost_per_rca_usd_median": round(median(costs), 4) if costs else None,
        }
    return {
        "by_llm_mode": by_mode,
        "note": "RCA accuracy (exact / directional) and PR acceptance come from evals/reports (P11).",
    }


def inbox(p: Paths, limit: int = 100) -> list[dict[str, Any]]:
    return list(reversed(_jsonl(p.inbox)[-limit:]))


def feedback(p: Paths, run_id: str | None = None) -> list[dict[str, Any]]:
    rows = _jsonl(p.feedback)
    return [r for r in rows if run_id is None or r.get("run_id") == run_id]


def add_feedback(p: Paths, entry: dict[str, Any]) -> dict[str, Any]:
    p.feedback.parent.mkdir(parents=True, exist_ok=True)
    row = {"at": datetime.now(UTC).isoformat(), **entry}
    with p.feedback.open("a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def _frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---"):
        return {}
    _, fm, _ = text.split("---", 2)
    return obj(yaml.safe_load(fm))


def marketplace(p: Paths) -> dict[str, Any]:
    """Skills (markdown in plugins), agent types and what they load, subagents, decision templates."""
    types: dict[str, Any] = {}
    for f in sorted((p.root / "configs" / "agent_types").glob("*.yaml")):
        cfg = yaml.safe_load(f.read_text())
        types[cfg.get("name", f.stem)] = {
            "description": cfg.get("description"),
            "nodes": {
                k: {kk: vv for kk, vv in v.items() if kk != "system_prompt"}
                for k, v in obj(cfg.get("nodes")).items()
            },
            "skills": sorted({n for names in obj(cfg.get("skills")).values() for n in arr(names)}),
            "skills_by_node": obj(cfg.get("skills")),
            "run_budget_usd": cfg.get("run_budget_usd"),
        }
    skills: list[dict[str, Any]] = []
    for f in sorted((p.root / "marketplace").glob("plugins/*/skills/*/SKILL.md")):
        text = f.read_text()
        fm = _frontmatter(text)
        name = str(fm.get("name", f.parent.name))
        skills.append(
            {
                "name": name,
                "plugin": f.parts[-4],
                "description": fm.get("description"),
                "tokens": len(text) // 4,
                "path": str(f.relative_to(p.root)),
                "used_by": [t for t, c in types.items() if name in (arr(c.get("skills")))]
                + (["pipeline (pr_and_notify)"] if name == "pr-authoring" else []),
            }
        )
    sub_file = p.root / "configs" / "subagents.yaml"
    subagents = obj(obj(yaml.safe_load(sub_file.read_text())).get("subagents")) if sub_file.is_file() else {}
    return {
        "agent_types": types,
        "skills": skills,
        "subagents": [
            {"id": k, **{kk: obj(v).get(kk) for kk in ("description", "inputs", "mcp_servers")}}
            for k, v in subagents.items()
        ],
        "templates": [
            {"id": t.id, "stage": t.stage, "model": t.model, "description": t.description}
            for t in sorted(templates().values(), key=lambda t: t.id)
        ],
    }
