"""Post-PR tools (SPEC §9): the diff fixer, Ask AI and "open in your machine".

* Diff fixer: one instruction ("use the existing helper") → an agent edits the run's sandboxed worktree;
  the same fix contract is re-proved (fails on the release, passes with the change, suite + CI checks);
  then commit, push (policy-gated) and a comment on the PR.
* Ask AI: a chat seeded with the run (RCA, claims, evidence, fix, proof). Answers cite evidence ids; a
  session is a JSONL file, so a conversation can be resumed. A message marked as a correction goes to D18.
* Open in your machine: a devcontainer + compose override pinned to the bad release and the fix branch,
  flags set to the user's exposure and the failing test ready; returns `vscode://` and shell commands.
"""

from __future__ import annotations

import json
import re
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from debugassist.core.policy import Verdict
from debugassist.core.settings import Integration, get_settings
from debugassist.integrations.sandbox import IMAGES
from debugassist.llm.spec import LLMNodeSpec
from debugassist.llm.workspace_tools import build_workspace_tools, changed_files
from debugassist.pipeline import nodes, skills
from debugassist.pipeline.deps import Deps, build_deps
from debugassist.pipeline.state import RunState

ASK_SYSTEM = """You answer an engineer's questions about one automated debugging run of DebugAssist on the
MiniRide app. You are given the run: issue, root cause, claims with evidence ids, timeline, evidence
summaries, the fix diff and the validation proof. Answer briefly and concretely. Every factual statement
cites the evidence ids it rests on, like [ev_logs_0123456789]; only cite ids that appear in the context.
If the context does not answer the question, say so and say what evidence would. If the engineer corrects
the analysis, acknowledge what changes and what still holds; do not argue."""

FIX_DIFF_SYSTEM = """You revise a bug fix that is already in the worktree (committed on this branch), following
one instruction from the reviewer. Make the smallest change that satisfies the instruction. The fix must
stay correct: the reproduction test must keep passing, it must still fail on the release without the
source change, and the component suite and the repository's CI checks must pass. Do not weaken the test.
When done, submit a conventional commit title and a one-paragraph summary of what you changed."""


class DiffFixOutput(BaseModel):
    commit_title: str = Field(
        description="conventional commit title, e.g. 'refactor(eta): reuse clampDelay helper'"
    )
    summary: str = Field(description="what changed and why, one paragraph")


class ChatAnswer(BaseModel):
    answer: str = Field(description="the answer, with evidence ids in [brackets]")
    evidence_ids: list[str] = Field(description="evidence ids cited in the answer")


def _load(run_id: str) -> tuple[RunState, Path]:
    from debugassist.core.policy import ROOT

    path = ROOT / ".data" / "runs" / run_id / "state.json"
    if "/" in run_id or ".." in run_id or not path.is_file():
        raise FileNotFoundError(f"no run {run_id}")
    return RunState.model_validate_json(path.read_text()), path


async def _deps(state: RunState) -> Deps:
    llm = get_settings().mode(Integration.LLM).value
    deps = await build_deps(state.run_id, mode=state.mode, llm_mode="live" if llm == "live" else "mock")
    # Act through the backends the run used: a mock PR is never pushed or commented on live.
    from debugassist.integrations.github import GitHubMock

    if state.pr and state.pr.mode == "mock":
        deps.github = GitHubMock()
    return deps


def _record(state: RunState, path: Path, entry: dict[str, Any]) -> None:
    state.post_pr.append(entry)
    path.write_text(state.model_dump_json(indent=2))


# ---- diff fixer -----------------------------------------------------------------------------


async def fix_diff(run_id: str, instruction: str) -> dict[str, Any]:
    state, path = _load(run_id)
    issue = state.issue
    if not (
        issue and state.fix_attempts and state.fix_attempts[-1].repro and state.fix_attempts[-1].repro_run
    ):
        raise ValueError("this run has no verified fix to revise")
    fa = state.fix_attempts[-1]
    repro = fa.repro
    assert repro
    deps = await _deps(state)
    entry: dict[str, Any] = {
        "kind": "diff_fix",
        "at": datetime.now(UTC).isoformat(),
        "instruction": instruction,
    }
    try:
        sb = nodes.sandbox_for(state)
        comp = nodes.component_cfg(state, sb.worktree)
        base = f"v{issue.last_version}"
        cmd = str(fa.repro_run["command"])
        before_head = _git(sb.worktree, "rev-parse", "HEAD")
        tools = build_workspace_tools(
            sb,
            allow_edits=True,
            allow_commands=True,
            editable=lambda p: not p.startswith(("src/vendor/", "vendor/")),
            workdir=issue.component,
        )
        if fa.tier == "e2e_env":
            tools.append(nodes.e2e_tool(sb, issue))
        cfg: dict[str, Any] = dict(deps.agent_type["nodes"]["fix"])
        cfg["max_turns"] = min(12, int(cfg["max_turns"]))
        spec = LLMNodeSpec(
            node="diff_fixer", system_prompt=FIX_DIFF_SYSTEM + skills.for_node(deps.agent_type, "fix"), **cfg
        )
        prompt = (
            f"Reviewer instruction: {instruction}\n\n"
            f"Repository {issue.repo}, component '{issue.component}'. Release {base}.\n"
            f"Root cause: {state.rca.output.root_cause if state.rca and state.rca.output else '-'}\n"
            f"Reproduction test: `{repro.test_file}` (`{cmd}`).\n\n"
            f"Current fix (diff against the release):\n```diff\n{fa.diff[-6000:]}\n```\n"
            "Apply the instruction, check the tests, then submit."
        )

        def check(_out: dict[str, Any]) -> str | None:
            if not _git(sb.worktree, "status", "--porcelain"):
                return "you have not changed anything yet"
            return nodes.fix_contract_problem(sb, issue, comp, base, cmd, repro.test_file)

        r = await deps.runner(None).run(
            spec, prompt, DiffFixOutput, tools=tools, diff_fn=lambda: sb.diff(base), validate_output=check
        )
        nodes.stop_if_out_of_quota(r, state, "diff_fixer")
        entry["llm"] = {k: v for k, v in nodes.llm_summary(r).items() if k != "tool_calls"}
        problem = check({}) if r.output else "the agent did not submit"
        if problem:
            subprocess.run(["git", "checkout", "-q", "--", "."], cwd=sb.worktree, check=False)
            subprocess.run(["git", "clean", "-qfd"], cwd=sb.worktree, check=False)
            entry |= {"status": "rejected", "reason": problem[:600]}
            return entry
        out = DiffFixOutput.model_validate(r.output)
        sha = sb.commit(f"{out.commit_title}\n\n{out.summary}\n\nRequested in review: {instruction[:300]}")
        entry |= {
            "status": "committed",
            "commit": sha[:12],
            "title": out.commit_title,
            "summary": out.summary,
            "diff": subprocess.run(
                ["git", "diff", before_head, "HEAD"],
                cwd=sb.worktree,
                capture_output=True,
                text=True,
                check=True,
            ).stdout[-8000:],
        }
        fa.diff = sb.diff(base)
        fa.files = changed_files(fa.diff)
        if state.pr:
            entry |= _push_and_comment(state, deps, sb.worktree, out, instruction)
        return entry
    finally:
        _record(state, path, entry)
        if deps.engine.ledger is not None:
            await deps.engine.ledger.close()


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False).stdout.strip()


def _push_and_comment(
    state: RunState, deps: Deps, worktree: Path, out: DiffFixOutput, instruction: str
) -> dict[str, Any]:
    pr, issue = state.pr, state.issue
    assert pr and issue
    push_v = deps.gate.verdict("github.push_branch", repo=issue.gh_repo, branch=pr.branch)
    comment_v = deps.gate.verdict("github.comment", repo=issue.gh_repo)
    result: dict[str, Any] = {"pushed": False, "commented": False}
    if push_v is Verdict.LIVE:
        deps.github.push(worktree, pr.branch)
        result["pushed"] = True
    if comment_v is Verdict.LIVE:
        deps.github.comment(
            issue.gh_repo,
            pr.number,
            f"**DebugAssist diff fixer** — requested: _{instruction[:300]}_\n\n{out.summary}\n\n"
            "Re-validated: the reproduction test still fails on the release and passes with the change; "
            "suite and CI checks pass.",
        )
        result["commented"] = True
    deps.gate.record(
        "github.push_branch", push_v, run_id=state.run_id, detail={"branch": pr.branch}, result=result
    )
    return result


# ---- Ask AI ---------------------------------------------------------------------------------


def _context(state: RunState, budget_chars: int = 24_000) -> tuple[str, set[str]]:
    issue, rca = state.issue, state.rca
    lines: list[str] = []
    known: set[str] = set()
    if issue:
        lines.append(f"Issue {issue.id} ({issue.source}): {issue.title} — {issue.app} {issue.last_version}")
    if rca and rca.output:
        o = rca.output
        lines += [
            f"Root cause ({o.category}): {o.root_cause}",
            f"Location: {o.location.file} → {o.location.function}",
        ]
        lines.append("Claims:")
        verdict = {g["text"]: g["grounding"] for g in rca.grounding}
        for c in o.claims:
            lines.append(f"- {c.text} [{', '.join(c.evidence_ids)}] ({verdict.get(c.text, 'unchecked')})")
            known.update(c.evidence_ids)
        lines.append("Timeline:")
        lines += [f"- {t.when}: {t.event} [{', '.join(t.evidence_ids)}]" for t in o.timeline]
    lines.append("Evidence:")
    for e in state.evidence:
        known.add(e.id)
        lines.append(f"- {e.id} ({e.source}): {e.summary} :: {json.dumps(e.data, default=str)[:600]}")
    if state.mitigation:
        lines.append(f"Mitigation: {state.mitigation.detail}")
    if state.fix_attempts:
        fa = state.fix_attempts[-1]
        lines.append(
            f"Fix ({fa.tier or '-'} test {fa.repro.test_file if fa.repro else '-'}):\n{fa.diff[-3000:]}"
        )
    if state.validation:
        lines.append(f"Validation passed: {state.validation.passed}")
    return "\n".join(lines)[-budget_chars:], known


def chat_dir(run_id: str) -> Path:
    from debugassist.core.policy import ROOT

    return ROOT / ".data" / "runs" / run_id / "chat"


def session(run_id: str, session_id: str) -> list[dict[str, Any]]:
    f = chat_dir(run_id) / f"{session_id}.jsonl"
    if not re.fullmatch(r"[a-f0-9]{12}", session_id) or not f.is_file():
        return []
    return [json.loads(line) for line in f.read_text().splitlines() if line.strip()]


def sessions(run_id: str) -> list[dict[str, Any]]:
    d = chat_dir(run_id)
    out: list[dict[str, Any]] = []
    for f in sorted(d.glob("*.jsonl")) if d.is_dir() else []:
        msgs = session(run_id, f.stem)
        if msgs:
            out.append(
                {
                    "session_id": f.stem,
                    "messages": len(msgs),
                    "started": msgs[0]["at"],
                    "first": msgs[0]["content"][:120],
                }
            )
    return out


def _append(run_id: str, session_id: str, msg: dict[str, Any]) -> None:
    d = chat_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    with (d / f"{session_id}.jsonl").open("a") as f:
        f.write(json.dumps(msg) + "\n")


async def ask(
    run_id: str, message: str, session_id: str | None = None, *, correction: bool = False
) -> dict[str, Any]:
    state, _ = _load(run_id)
    sid = session_id if session_id and re.fullmatch(r"[a-f0-9]{12}", session_id) else uuid.uuid4().hex[:12]
    history = session(run_id, sid)
    _append(
        run_id,
        sid,
        {"role": "user", "content": message, "correction": correction, "at": datetime.now(UTC).isoformat()},
    )
    context, known = _context(state)
    convo = "\n".join(f"{m['role']}: {m['content']}" for m in history[-12:])
    deps = await _deps(state)
    try:
        spec = LLMNodeSpec(
            node="ask_ai",
            system_prompt=ASK_SYSTEM,
            reasoning_effort="low",
            max_turns=3,
            max_tool_calls=0,
            max_budget_usd=0.05,
        )
        r = await deps.runner(None).run(
            spec,
            f"Run context:\n{context}\n\nConversation so far:\n{convo or '(new)'}\n\nEngineer: {message}\n\nAnswer with submit_result.",
            ChatAnswer,
        )
        if r.output:
            a = ChatAnswer.model_validate(r.output)
            cited = [e for e in a.evidence_ids if e in known]
            unknown = sorted(set(re.findall(r"ev_[a-z_]+_[0-9a-f]{6,}", a.answer)) - known)
            reply: dict[str, Any] = {"answer": a.answer, "evidence_ids": cited, "unknown_citations": unknown}
        else:
            reply = {
                "answer": "No answer: the LLM is in mock mode or did not respond."
                if r.mode == "mock"
                else f"No answer ({r.status}).",
                "evidence_ids": [],
                "unknown_citations": [],
            }
        reply |= {"cost_usd": r.cost_usd, "mode": r.mode}
        routed = None
        if correction:
            from debugassist.pipeline import feedback

            routed = await feedback.route(
                state, deps, {"target": "chat", "reaction": "down", "comment": message}
            )
        _append(
            run_id,
            sid,
            {
                "role": "assistant",
                "content": reply["answer"],
                "evidence_ids": reply["evidence_ids"],
                "at": datetime.now(UTC).isoformat(),
            },
        )
        return {"session_id": sid, **reply, "routed": routed}
    finally:
        if deps.engine.ledger is not None:
            await deps.engine.ledger.close()


# ---- open in your machine -------------------------------------------------------------------


def open_env(run_id: str) -> dict[str, Any]:
    """Write a devcontainer + compose override for the run and return how to open it."""
    state, _ = _load(run_id)
    issue = state.issue
    if issue is None:
        raise ValueError("run has no issue")
    sb = nodes.sandbox_for(state)
    if not sb.worktree.is_dir():
        raise ValueError("the run's worktree is gone; re-run to recreate it")
    out = sb.worktree.parent / "open"
    (out / ".devcontainer").mkdir(parents=True, exist_ok=True)
    comp = nodes.component_cfg(state, sb.worktree)
    fa = state.fix_attempts[-1] if state.fix_attempts else None
    bad = f"v{issue.last_version}"
    fix_branch = state.pr.branch if state.pr else _git(sb.worktree, "branch", "--show-current")
    flags: dict[str, Any] = (
        (state.fix_plan.captured_env.get("flags") if state.fix_plan else None)
        or issue.latest_event.get("flags")
        or issue.report.get("flags")
        or {}
    )
    test_cmd = str(fa.repro_run.get("command")) if fa and fa.repro_run else str(comp["test"])
    workdir = f"/work/{issue.component}".rstrip("/.")
    devcontainer = {
        "name": f"DebugAssist {issue.id}",
        "image": IMAGES.get(issue.language, "node:22-alpine"),
        "workspaceMount": f"source={sb.worktree},target=/work,type=bind",
        "workspaceFolder": workdir,
        "postCreateCommand": str(comp["setup"]),
        "containerEnv": {"DEBUGASSIST_RUN": run_id, "DEBUGASSIST_FLAGS": json.dumps(flags)},
        "customizations": {"vscode": {"extensions": ["vitest.explorer", "ms-playwright.playwright"]}},
    }
    (out / ".devcontainer" / "devcontainer.json").write_text(json.dumps(devcontainer, indent=2) + "\n")
    services = {"miniride-client": "client", "miniride-services": "gateway"}
    override = (
        "# docker compose -f infra/docker-compose.yml -f <this file> up -d --build\n"
        f"# Builds {services.get(issue.repo, 'client')} from this run's worktree (the fix branch {fix_branch}).\n"
        "services:\n"
        f"  {services.get(issue.repo, 'client')}:\n"
        f"    build:\n      context: {sb.worktree}\n"
    )
    (out / "compose.override.yml").write_text(override)
    readme = "\n".join(
        [
            f"# {issue.id}: {issue.title}",
            "",
            f"- Worktree: `{sb.worktree}` (branch `{fix_branch}`)",
            f"- See the bug: `git -C {sb.worktree} stash; git -C {sb.worktree} checkout {bad}`",
            f"- Failing test (fails on {bad}, passes on the fix): `{test_cmd}`",
            f"- Flags the user had: `{json.dumps(flags)}` (set them in Unleash: http://localhost:4242)",
            f"- Run the stack with this fix: `docker compose -f infra/docker-compose.yml -f {out / 'compose.override.yml'} up -d --build`",
            "",
        ]
    )
    (out / "README.md").write_text(readme)
    return {
        "dir": str(out),
        "worktree": str(sb.worktree),
        "vscode": f"vscode://file{sb.worktree}",
        "devcontainer": str(out / ".devcontainer" / "devcontainer.json"),
        "commands": [
            f"code {sb.worktree}",
            f"cd {sb.worktree if issue.component == '.' else sb.worktree / issue.component} && {test_cmd}",
        ],
        "bad_ref": bad,
        "fix_branch": fix_branch,
        "flags": flags,
        "test_command": test_cmd,
    }
