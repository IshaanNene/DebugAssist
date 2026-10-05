"""Feedback loop (D18): a developer's reaction or correction is classified by Clef and routed by code.

* A bare 👍/👎 labels the decisions behind what was rated (the RCA → D05; a claim → its D09 grounding
  check), which the Metrics screen turns into accuracy and Brier scores.
* With a comment, D18 classifies it:
  - root cause / location → label store + the prompt-improvement log (what the RCA prompt got wrong);
  - fix approach / style → a proposed skill update: the lesson appended to the fix skill on a local
    `debugassist/skill-…` branch with a marketplace PR record (pushing this repo is outside the write
    policy, so a human opens the real PR);
  - praise → label store; other / low confidence → posted to the owner in chat.
"""

from __future__ import annotations

import json
import re
import subprocess
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from debugassist.core.policy import ROOT, Verdict
from debugassist.core.redaction import redact_text
from debugassist.decisions.engine import RunContext
from debugassist.decisions.state import CompactState
from debugassist.integrations.chat import ChatMessage
from debugassist.pipeline import collector, skills
from debugassist.pipeline.deps import Deps
from debugassist.pipeline.state import RunState

DATA = ROOT / ".data"
MARKETPLACE_REPO = "IshaanNene/DebugAssist"


def _append(name: str, row: dict[str, Any]) -> None:
    DATA.mkdir(exist_ok=True)
    with (DATA / name).open("a") as f:
        f.write(json.dumps({"at": datetime.now(UTC).isoformat(), **row}) + "\n")


def _target_text(state: RunState, target: str) -> str:
    o = state.rca.output if state.rca else None
    if o is None:
        return ""
    if m := re.fullmatch(r"claim:(\d+)", target):
        i = int(m.group(1))
        return o.claims[i].text if i < len(o.claims) else ""
    return o.summary


def _mentions(questions: Any, text: str) -> bool:
    """Does any question's instruction quote this claim? (Compared as text: JSON would escape quotes.)"""
    if not isinstance(questions, dict):
        return False
    for q in cast(dict[str, Any], questions).values():
        if isinstance(q, dict) and text in str(cast(dict[str, Any], q).get("instructions", "")):
            return True
    return False


async def label_decisions(state: RunState, deps: Deps, target: str, up: bool, comment: str) -> list[str]:
    """Attach the reviewer's verdict to the ledger rows that produced what was rated."""
    ledger = deps.engine.ledger
    if ledger is None:
        return []
    rows = await ledger.list(run_id=state.run_id)
    labelled: list[str] = []
    text = _target_text(state, target)
    if target.startswith("claim:") and text:
        verdict = next(
            (g["grounding"] for g in (state.rca.grounding if state.rca else []) if g["text"] == text), None
        )
        for r in rows:
            if r.decision_id.startswith("D09") and _mentions(r.questions, text):
                outcome: dict[str, Any] = {"claim_true": up, "comment": comment[:300]}
                if verdict in ("supported", "unsupported"):
                    outcome["correct"] = (verdict == "supported") == up
                await ledger.label(r.id, outcome, source="review")
                labelled.append(r.id)
    elif target in ("rca", "chat"):
        for r in rows:
            if r.decision_id.startswith("D05"):
                await ledger.label(r.id, {"correct": up, "comment": comment[:300]}, source="review")
                labelled.append(r.id)
    return labelled


def propose_skill_update(state: RunState, deps: Deps, kind: str, comment: str) -> dict[str, Any]:
    """Append the lesson to the fix skill on a local branch and record a marketplace PR (never pushed)."""
    by_node: dict[str, list[str]] = deps.agent_type.get("skills") or {}
    names = by_node.get("fix") or []
    path = skills.find(names[0]) if names else None
    if path is None:
        return {"status": "no_skill", "detail": "the agent type lists no fix skill"}
    issue = state.issue
    assert issue
    pid = uuid.uuid4().hex[:8]
    branch = f"debugassist/skill-{names[0]}-{pid}"
    lesson = f"- {redact_text(comment.strip())} _({kind.replace('_', ' ')}; review of {issue.id}, {datetime.now(UTC).date()})_"
    work = DATA / "proposals" / pid
    rel = path.relative_to(ROOT)

    def git(*args: str, cwd: Any = ROOT) -> str:
        return subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
        ).stdout.strip()

    git("worktree", "add", "-q", "-b", branch, str(work), "HEAD")
    try:
        target = work / rel
        current = (
            target if target.is_file() else path
        )  # a skill not committed yet: start from the working copy
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(current.read_text().rstrip("\n") + "\n" + lesson + "\n")
        git("add", str(rel), cwd=work)
        git(
            "-c", "user.name=DebugAssist Bot", "-c", "user.email=debugassist-bot@users.noreply.github.com",
            "commit", "-q", "-m", f"docs(skills): lesson from review of {issue.id}\n\n{comment[:500]}",
            cwd=work,
        )  # fmt: skip
        patch = git("format-patch", "-1", "--stdout", cwd=work)
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(work)], cwd=ROOT, capture_output=True)
    verdict = deps.gate.verdict("github.open_pr", repo=MARKETPLACE_REPO)  # outside the policy's repos → deny
    record: dict[str, Any] = {
        "id": pid,
        "repo": MARKETPLACE_REPO,
        "branch": branch,
        "skill": names[0],
        "file": str(rel),
        "lesson": lesson,
        "title": f"docs(skills): lesson from review of {issue.id}",
        "patch": patch,
        "run_id": state.run_id,
        "pushed": verdict is Verdict.LIVE,
    }
    out = DATA / "mock" / "github" / f"marketplace-pr-{pid}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2))
    deps.gate.record(
        "github.open_pr",
        verdict,
        run_id=state.run_id,
        detail={"repo": MARKETPLACE_REPO, "branch": branch},
        result="proposed locally",
    )
    return {"status": "proposed", "branch": branch, "record": str(out.relative_to(ROOT)), "lesson": lesson}


async def route(state: RunState, deps: Deps, entry: dict[str, Any]) -> dict[str, Any]:
    target, up = str(entry.get("target", "rca")), entry.get("reaction") == "up"
    comment = str(entry.get("comment") or "").strip()
    issue = state.issue
    assert issue
    out: dict[str, Any] = {"target": target, "reaction": entry.get("reaction")}
    out["labelled"] = await label_decisions(state, deps, target, up, comment)
    if not comment:
        out["action"] = "label_store"
        _append("labels.jsonl", {"run_id": state.run_id, "issue_id": issue.id, **out})
        return out
    cs = (
        CompactState()
        .add("comment", redact_text(comment), priority=0)
        .add(
            "rated",
            {"target": target, "reaction": entry.get("reaction"), "text": _target_text(state, target)},
            priority=0,
        )
        .add("issue", collector.issue_summary(issue), priority=1)
    )
    d = await deps.engine.decide("D18", cs, ctx=RunContext(run_id=state.run_id, issue_id=issue.id))
    kind = str(d.chosen.get("kind", "other"))
    out |= {"kind": kind, "p": d.p, "band": d.band, "action": d.action, "ledger": d.ledger_id}
    if d.action == "label_store":
        _append("labels.jsonl", {"run_id": state.run_id, "issue_id": issue.id, "comment": comment, **out})
        if kind in ("root_cause", "location"):
            _append(
                "prompt_log.jsonl",
                {"node": "classify_rca", "run_id": state.run_id, "kind": kind, "comment": comment},
            )
    elif d.action == "skill_update":
        out["proposal"] = propose_skill_update(state, deps, kind, comment)
        _append("prompt_log.jsonl", {"node": "fix", "run_id": state.run_id, "kind": kind, "comment": comment})
    else:
        from debugassist.pipeline.nodes import _notify  # pyright: ignore[reportPrivateUsage]

        tr = state.triage
        msg = ChatMessage(
            to=f"@{tr.oncall}" if tr else "#debugassist",
            title=f"Review feedback on {issue.id} needs a human",
            text=comment[:1500],
            level="warning",
            links={"Issue": issue.url, "PR": state.pr.url if state.pr else ""},
            fields={"Rated": target, "Clef D18": f"{kind} (p={d.p:.2f})" if d.p is not None else kind},
        )
        out["chat"] = _notify(deps, state.run_id, msg)
    return out
