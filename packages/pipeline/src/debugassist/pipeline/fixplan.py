"""Fix plan, decided once before the first fix attempt (N5): Clef decides, code gathers and acts.

* D12 localization: code lists candidate functions (the RCA's location, stack frames, files the RCA
  mentions, files changed in the release that introduced the bug, definitions of identifiers the root
  cause names); Clef picks where the fix belongs (two-stage when there are many).
* The commits in the release window that touched the chosen file are listed deterministically, as a
  check on the RCA's suspect commit.
* D13 picks the fix strategy; "needs a human" stops before any code is written. "Flag only" stops
  only if the flag was actually rolled back; otherwise users would stay broken.
* D14 picks the cheapest test tier; the ladder climbs from there (unit → integration → E2E with the
  captured environment), then falls back to the cheaper tiers. Tiers that cannot run here are left out.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from debugassist.decisions.engine import RunContext
from debugassist.decisions.state import CompactState
from debugassist.integrations.sandbox import Sandbox
from debugassist.llm.workspace_tools import is_test_path
from debugassist.pipeline import collector, e2e
from debugassist.pipeline.deps import Deps
from debugassist.pipeline.state import TIERS, FixPlan, Issue, RunState, Tier

MAX_CANDIDATES = 80
SOURCE_EXT = {"typescript": (".ts", ".tsx"), "python": (".py",), "go": (".go",)}
NOT_FUNCTIONS = {"if", "for", "while", "switch", "catch", "return", "function", "constructor", "super"}
DEFS = {
    "typescript": [
        re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)"),
        re.compile(
            r"^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?:async\s*)?"
            r"(?:function\b|\([^)]*\)\s*(?::\s*[^=]+)?=>|[A-Za-z_$][\w$]*\s*=>)"
        ),
        re.compile(
            r"^\s+(?:(?:public|private|protected|static|readonly|override|async)\s+)*([A-Za-z_$][\w$]*)\s*\([^;]*\)\s*(?::\s*[^={;]+)?\{\s*$"
        ),
    ],
    "python": [re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)")],
    "go": [re.compile(r"^func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)")],
}
CLASS = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)")
PATH_RE = re.compile(r"(?:[\w.-]+/)*[\w.-]+\.(?:tsx?|py|go)\b")
IDENT_RE = re.compile(r"`([A-Za-z_$][\w$.]*)(?:\(\))?`")


def _ctx(state: RunState) -> RunContext:
    assert state.issue
    return RunContext(run_id=state.run_id, issue_id=state.issue.id)


def _git(sb: Sandbox, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=sb.worktree, capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else ""


def release_window(sb: Sandbox, issue: Issue) -> tuple[str, str] | None:
    """(previous release tag, tag of the release where the bug first appeared)."""
    first = f"v{issue.first_version or issue.last_version}"
    tags = _git(sb, "tag", "--list", "v*", "--sort=-v:refname").splitlines()
    if first not in tags:
        return None
    older = tags[tags.index(first) + 1 :]
    return (older[0], first) if older else None


def functions(path: Path, language: str) -> list[tuple[str, int, str]]:
    """(qualified name, line, signature) for every function/method defined in a source file."""
    out: list[tuple[str, int, str]] = []
    cls: str | None = None
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return out
    for i, line in enumerate(lines, 1):
        if m := CLASS.match(line):
            cls = m.group(1)
            continue
        if line.startswith("}") or (language == "python" and line[:1].strip()):
            cls = None  # end of a TS class body, or a top-level Python statement
        for rx in DEFS.get(language, []):
            m = rx.match(line)
            if m and m.group(1) not in NOT_FUNCTIONS:
                indented = line[:1].isspace()
                name = f"{cls}.{m.group(1)}" if cls and indented else m.group(1)
                out.append((name, i, line.strip()[:160]))
                break
    return out


def candidates(sb: Sandbox, state: RunState) -> tuple[list[dict[str, str]], list[str]]:
    """Candidate fix locations ("path::function") with why each is a candidate; plus the release window's
    changed files."""
    issue, rca = state.issue, state.rca
    assert issue and rca and rca.output
    o = rca.output
    root = sb.worktree
    exts = SOURCE_EXT.get(issue.language, ())

    def src(rel: str) -> bool:
        rel_in = rel.removeprefix("./")
        return (
            rel_in.endswith(exts)
            and not is_test_path(rel_in)
            and "vendor/" not in rel_in
            and (root / rel_in).is_file()
        )

    reasons: dict[str, list[str]] = {}

    def add(rel: str, why: str) -> None:
        rel = rel.removeprefix("./")
        if src(rel) and why not in reasons.setdefault(rel, []):
            reasons[rel].append(why)

    add(o.location.file, "RCA location")
    frames: list[dict[str, Any]] = issue.latest_event.get("frames") or []
    for f in frames:
        if f.get("in_app", True) and f.get("file"):
            add(str(f["file"]).split("?")[0].split("://")[-1].lstrip("/"), "stack frame")
    text = " ".join([o.summary, o.root_cause, o.fix_direction, *(c.text for c in o.claims)])
    for p in PATH_RE.findall(text):
        add(p, "mentioned in the RCA")
    changed: list[str] = []
    if window := release_window(sb, issue):
        changed = [
            f for f in _git(sb, "diff", "--name-only", f"{window[0]}..{window[1]}").splitlines() if src(f)
        ]
        for f in changed:
            add(f, f"changed in {window[1]}")
    idents = {i.split(".")[-1] for i in IDENT_RE.findall(text) if len(i.split(".")[-1]) > 2}
    if o.location.function:
        idents.add(o.location.function.split(".")[-1])
    # Callers: only distinctive names (camelCase, snake_case or long), plus the class owning the RCA function.
    search = {i for i in idents if len(i) >= 6 or re.search(r"[A-Z_]", i)}
    for name, _, _ in functions(root / o.location.file.removeprefix("./"), issue.language):
        if "." in name and name.split(".")[-1] == o.location.function.split(".")[-1]:
            search.add(name.split(".")[0])
    if search:
        comp = root if issue.component == "." else root / issue.component
        word = re.compile(r"\b(" + "|".join(re.escape(i) for i in sorted(search)) + r")\b")
        for path in comp.rglob("*"):
            rel = str(path.relative_to(root))
            if "node_modules" in path.parts or not src(rel) or rel in reasons:
                continue
            try:
                hits = set(word.findall(path.read_text(errors="replace")))
            except OSError:
                continue
            if hits:
                add(rel, f"references {', '.join(f'`{h}`' for h in sorted(hits)[:3])}")

    def weight(rel: str) -> int:
        w = {"RCA location": 4, "stack frame": 3, "mentioned in the RCA": 2}
        return sum(w.get(r, 1) for r in reasons[rel])

    out: list[dict[str, str]] = []
    target = (o.location.file.removeprefix("./"), o.location.function.split(".")[-1])
    for rel in sorted(reasons, key=lambda r: -weight(r)):
        for name, line, sig in functions(root / rel, issue.language):
            short = name.split(".")[-1]
            why = list(reasons[rel])
            if (rel, short) == target:
                why.insert(0, "RCA function")
            elif short in idents:
                why.insert(0, "named in the RCA")
            out.append({"id": f"{rel}::{name}", "summary": f"{sig} (line {line}) — {', '.join(why)}"})
    return out[:MAX_CANDIDATES], changed


def suspect_commits(sb: Sandbox, issue: Issue, files: list[str]) -> list[dict[str, str]]:
    window = release_window(sb, issue)
    if not window or not files:
        return []
    log = _git(sb, "log", "--format=%h%x09%s", f"{window[0]}..{window[1]}", "--", *files)
    return [
        {"sha": sha, "subject": subj, "window": f"{window[0]}..{window[1]}"}
        for sha, _, subj in (line.partition("\t") for line in log.splitlines())
    ]


async def localize(
    sb: Sandbox, state: RunState, deps: Deps
) -> tuple[dict[str, Any], list[str], int, str | None]:
    """D12: (decision record, focus locations, number of candidates, ledger id)."""
    issue, rca = state.issue, state.rca
    assert issue and rca and rca.output
    cands, _ = candidates(sb, state)
    if not cands:
        return {"action": "search_wider", "reason": "no candidates found"}, [], 0, None
    o = rca.output
    cs = (
        CompactState()
        .add("issue", collector.issue_summary(issue), priority=0)
        .add(
            "rca",
            {"summary": o.summary, "root_cause": o.root_cause, "fix_direction": o.fix_direction},
            priority=0,
        )
    )
    # Clef question ids allow only [A-Za-z0-9_.-] (two-stage asks one question per candidate): use
    # opaque ids and put the location in the description.
    by_key = {f"c{i + 1}": c["id"] for i, c in enumerate(cands)}
    params = [
        {"id": k, "summary": f"{by_key[k]}: {c['summary']}"} for k, c in zip(by_key, cands, strict=True)
    ]
    d = await deps.engine.decide("D12", cs, params={"candidates": params}, ctx=_ctx(state))
    key = str(d.chosen.get("location", ""))
    choice = by_key.get(key, key)
    rec = {"choice": choice, "p": d.p, "band": d.band, "action": d.action}
    if d.action == "focus_location" and key in by_key:
        focus = [choice]
    elif d.action == "give_top_k":
        dist: dict[str, float] = (d.probabilities or {}).get("location", {})
        ranked = sorted((k for k in dist if k in by_key), key=lambda k: -dist[k])
        focus = [by_key[k] for k in ranked[:3]] or [c["id"] for c in cands[:3]]
    else:
        focus = []
    return rec, focus, len(cands), d.ledger_id


async def choose_strategy(
    state: RunState, deps: Deps, focus: list[str], commits: list[dict[str, str]]
) -> tuple[dict[str, Any], str | None, str | None]:
    """D13: (decision record, skip reason or None, ledger id)."""
    issue, rca = state.issue, state.rca
    assert issue and rca and rca.output
    o = rca.output
    m = state.mitigation
    cs = (
        CompactState()
        .add(
            "rca",
            {
                "category": o.category,
                "summary": o.summary,
                "root_cause": o.root_cause,
                "fix_direction": o.fix_direction,
            },
            priority=0,
        )
        .add("location", focus or [f"{o.location.file}::{o.location.function}"], priority=0)
        .add("commits_in_release_window", commits[:5], priority=1)
        .add("mitigation", {"flag": m.flag, "action": m.action} if m else {}, priority=1)
    )
    d = await deps.engine.decide("D13", cs, ctx=_ctx(state))
    rec = {"choice": d.chosen.get("strategy"), "p": d.p, "band": d.band, "action": d.action}
    skip = None
    if d.action == "escalate_to_owner":
        skip = "needs a human decision (D13)"
    elif d.action == "skip_fix":
        if m and m.action == "rolled_back":
            skip = f"flag-only mitigation: {m.flag} rolled back (D13)"
        else:
            rec["note"] = "flag-only ignored: the flag was not rolled back, so a code fix is still needed"
    return rec, skip, d.ledger_id


async def choose_tier(
    state: RunState, deps: Deps, e2e_unavailable: str | None, env: dict[str, Any]
) -> tuple[dict[str, Any], list[Tier], str | None, str | None]:
    """D14: (decision record, ladder, skip reason or None, ledger id)."""
    issue, rca = state.issue, state.rca
    assert issue and rca and rca.output
    o = rca.output
    cs = (
        CompactState()
        .add("issue", collector.issue_summary(issue), priority=0)
        .add("rca", {"root_cause": o.root_cause, "reproduction_idea": o.reproduction}, priority=0)
        .add("captured_environment", env, priority=1)
        .add("e2e_available", e2e_unavailable is None, priority=1)
    )
    d = await deps.engine.decide("D14", cs, ctx=_ctx(state))
    rec: dict[str, Any] = {"choice": d.chosen.get("tier"), "p": d.p, "band": d.band, "action": d.action}
    start: Tier = {"tier_integration": "integration", "tier_e2e": "e2e_env"}.get(d.action or "", "unit")  # pyright: ignore[reportAssignmentType]
    if d.action == "tier_none":
        return rec, [], "cannot be reproduced automatically (D14)", d.ledger_id
    # From the choice upwards, then the cheaper tiers as a fallback if the choice can't reproduce it.
    ladder: list[Tier] = [*TIERS[TIERS.index(start) :], *TIERS[: TIERS.index(start)]]
    if e2e_unavailable is not None and "e2e_env" in ladder:
        ladder.remove("e2e_env")
        rec["e2e_unavailable"] = e2e_unavailable
    return rec, ladder, None, d.ledger_id


async def plan(
    sb: Sandbox, state: RunState, deps: Deps, pipeline: dict[str, Any]
) -> tuple[FixPlan, list[str]]:
    issue = state.issue
    assert issue
    ledgers: list[str] = []
    loc, focus, n, l12 = await localize(sb, state, deps)
    ledgers.append(l12 or "")
    files = sorted({f.split("::")[0] for f in focus})
    commits = suspect_commits(sb, issue, files)
    strategy, skip, l13 = await choose_strategy(state, deps, focus, commits)
    ledgers.append(l13 or "")
    env = e2e.captured_env(issue.report, issue.latest_event, state.evidence)
    unavailable = (
        e2e.unavailable(sb, pipeline, issue.component)
        if issue.language == "typescript"
        else "no E2E setup for this language"
    )
    tier, ladder, skip_tier, l14 = await choose_tier(state, deps, unavailable, env)
    ledgers.append(l14 or "")
    p = FixPlan(
        candidates=n,
        location=loc,
        focus=focus,
        suspect_commits=commits,
        strategy=strategy,
        tier=tier,
        ladder=ladder,
        captured_env=env,
        skip=skip or skip_tier,
    )
    return p, ledgers


def prompt_section(p: FixPlan) -> str:
    lines: list[str] = []
    if p.focus:
        label = "Fix location" if len(p.focus) == 1 else "Most likely fix locations"
        lines.append(f"{label}: {', '.join(p.focus)}")
    if p.suspect_commits:
        lines.append(
            "Commits that touched it in the release that introduced the bug: "
            + "; ".join(f"{c['sha']} {c['subject']}" for c in p.suspect_commits[:3])
        )
    strategy = p.strategy.get("choice")
    if strategy and p.strategy.get("action") == "apply_strategy":
        lines.append(f"Fix strategy: {str(strategy).replace('_', ' ')}")
    return "\n".join(lines) + ("\n" if lines else "")


TIER_GUIDE: dict[Tier, str] = {
    "unit": "Test tier: UNIT — a focused unit test of the faulty function/module (mock collaborators).",
    "integration": (
        "Test tier: INTEGRATION/COMPONENT — exercise the real modules together (e.g. render the component "
        "or call the service handler) and mock only the network/IO boundary."
    ),
    "e2e_env": (
        "Test tier: E2E WITH THE USER'S ENVIRONMENT — write a Playwright spec under `e2e/` that drives the "
        "app like the user did, emulating their captured environment, and asserts the correct outcome. "
        "Run it with the run_e2e tool (it builds the app and runs the spec against the live backends; about a "
        "minute), then submit. A crash shows up as an uncaught page error, not a failed step: collect "
        '`page.on("pageerror")` messages and assert the list is empty, so the failure prints the error.'
    ),
}
