"""The proof path, hermetically (audit P2-9, P2-8, P3-16): fix → validate → ship_gate → pr_and_notify on a toy
repository with a release tag and an injected bug, a sandbox that runs commands locally, and scripted agents.

The run's worktree is a linked `git worktree` of the toy repository, as in a real run, so host git goes through
`core.hostgit` exactly as it does there.
"""

from __future__ import annotations

import asyncio
import json
import shlex
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver

from debugassist.core import hostgit
from debugassist.core.policy import Verdict
from debugassist.integrations.github import PullRequest
from debugassist.integrations.sandbox import CommandResult
from debugassist.llm.spec import LLMResult
from debugassist.pipeline import graph, nodes, release
from debugassist.pipeline.state import (
    FixAttempt,
    FixPlan,
    ReproOutput,
    RunState,
    Ship,
    Validation,
)

FIXTURE = Path(__file__).parent / "fixtures" / "run_state.json"
BASE = "v1.0.0"
BRANCH = "debugassist/toy-1"

# The release, with the bug: head(xs, 0) returns the first element.
RELEASE = "def head(xs, n=1):\n    return xs[:n] if n > 0 else xs[:1]\n"
FIXED = "def head(xs, n=1):\n    return xs[: max(n, 0)]\n"
BROKEN = "def head(xs, n=1):\n    return []\n"  # "fixes" the report, breaks every other use
EXISTING = "from lib import head\n\nassert head([1, 2], 1) == [1]\n"
REPRO = "from lib import head\n\nassert head([1, 2], 0) == [], head([1, 2], 0)\n"
PASSING = "from lib import head\n\nassert head([1, 2], 2) == [1, 2]\n"  # does not reproduce anything
WEAK = "from lib import head\n\nassert True\n"
CHECK = """import pathlib, runpy, sys

files = sys.argv[1:] or sorted(str(p) for p in pathlib.Path("tests").glob("test_*.py"))
failed = 0
for f in files:
    try:
        runpy.run_path(f)
        print(f"PASSED {f}")
    except Exception as e:
        print(f"FAILED {f}: {type(e).__name__}: {e}")
        failed += 1
sys.exit(1 if failed else 0)
"""
PIPELINE = (
    "version: 1\ncomponents:\n  .:\n    path: .\n    language: python\n    setup: 'true'\n"
    "    test: python check.py\n    test_file_glob: tests/test_*.py\n"
)


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def toy_repo(tmp_path: Path) -> Path:
    """The target repository at its release tag, and a run worktree (linked, on the bot branch) at that tag."""
    origin = tmp_path / "origin"
    (origin / "tests").mkdir(parents=True)
    (origin / ".DebugAssist").mkdir()
    (origin / "lib.py").write_text(RELEASE)
    (origin / "check.py").write_text(CHECK)
    (origin / "tests" / "test_lib.py").write_text(EXISTING)
    (origin / ".DebugAssist" / "pipeline.yaml").write_text(PIPELINE)
    (origin / ".gitignore").write_text("node_modules/\n__pycache__/\n")
    git(origin, "init", "-q", "-b", "main")
    git(origin, "add", ".")
    git(origin, "commit", "-qm", "release 1.0.0")
    git(origin, "tag", BASE)
    wt = tmp_path / "runs" / "r1" / "repo"
    wt.parent.mkdir(parents=True)
    git(origin, "worktree", "add", "-q", "-B", BRANCH, str(wt), BASE)
    return wt


@dataclass
class FakeSandbox:
    """Runs the toy suite (`python check.py [test file]`) locally; `checkout()` as the real sandbox does."""

    worktree: Path
    run_worktree: Path
    log: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])
    crash_in_checkout: bool = False

    def run(
        self, command: str, *, workdir: str = ".", network: bool = False, timeout: int = 600
    ) -> CommandResult:
        where = "worktree" if self.worktree == self.run_worktree else "checkout"
        self.log.append((where, command))
        if self.crash_in_checkout and where == "checkout":
            raise RuntimeError("the host died mid-check")
        last = shlex.split(command)[-1]
        args = [last] if last.endswith(".py") and last != "check.py" else []
        cwd = self.worktree / workdir
        p = subprocess.run(
            [sys.executable, "check.py", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            env={"PYTHONPATH": str(cwd), "PYTHONDONTWRITEBYTECODE": "1"},
        )
        return CommandResult(command, p.returncode, p.stdout + p.stderr)

    def install(self, setup: str, workdir: str = ".") -> CommandResult:
        return CommandResult(setup, 0, "")

    def diff(self, base: str = "HEAD") -> str:
        hostgit.run(self.worktree, "add", "-A", "--intent-to-add", ".", check=True)
        return hostgit.run(self.worktree, "diff", base, "--", ".", check=True).stdout

    def commit(self, message: str) -> str:
        hostgit.run(self.worktree, "add", "-A", "--", ".", check=True)
        hostgit.run(
            self.worktree, "-c", "user.name=b", "-c", "user.email=b@b", "commit", "-qm", message, check=True
        )
        return hostgit.run(self.worktree, "rev-parse", "HEAD", check=True).stdout.strip()

    def checkout(self, root: Path) -> FakeSandbox:
        return FakeSandbox(root, self.run_worktree, self.log, self.crash_in_checkout)


Action = Callable[[dict[str, BaseTool]], dict[str, Any]]


def writes(path: str, content: str, **out: Any) -> Action:
    def act(tools: dict[str, BaseTool]) -> dict[str, Any]:
        tools["write_file"].invoke({"path": path, "content": content})
        return out

    return act


def does(*steps: Action, **out: Any) -> Action:
    def act(tools: dict[str, BaseTool]) -> dict[str, Any]:
        for step in steps:
            step(tools)
        return out

    return act


REPRO_OUT = {"test_file": "tests/test_repro.py", "asserts": "head(xs, 0) == []", "failure": "AssertionError"}
FIX_OUT = {
    "summary": "head returns nothing for n <= 0",
    "rationale": "xs[:1] was the fallback",
    "strategy": "clamp",
    "risk": "low",
    "commit_title": "fix(lib): head(xs, 0) returns []",
    "tests_added": ["tests/test_repro.py"],
}


@dataclass
class ScriptedAgent:
    """Stands in for the LLM runner: each node (by name prefix) acts through the tools it was given."""

    script: dict[str, Action]
    feedback: dict[str, str | None] = field(default_factory=dict[str, str | None])

    def __call__(self, apply_diff: Any = None) -> ScriptedAgent:
        return self

    async def run(self, spec: Any, prompt: str, schema: Any, **kw: Any) -> LLMResult:
        key = next(k for k in self.script if spec.node.startswith(k))
        out = self.script[key]({t.name: t for t in kw["tools"]})
        kw["diff_fn"]()  # as the real runner does: marks new files intent-to-add
        self.feedback[spec.node] = kw["validate_output"](out)
        return LLMResult(
            node=spec.node,
            output=out,
            status="ok",
            turns=1,
            tool_calls=[],
            model="scripted",
            mode="mock",
            cost_usd=0.001,
        )


@dataclass
class FakeEngine:
    actions: dict[str, str]
    calls: list[str] = field(default_factory=list[str])
    ledger: None = None

    async def decide(self, decision_id: str, *_: Any, **__: Any) -> Any:
        self.calls.append(decision_id)
        action = self.actions.get(decision_id, "stop")
        return SimpleNamespace(action=action, chosen={"risk": 1.0}, p=0.9, band="act", ledger_id=decision_id)


@dataclass
class FakeGate:
    """Pushes and PRs live (to the fake GitHub), everything else dry-run; ready PRs allowed."""

    records: list[tuple[str, Verdict]] = field(default_factory=list[tuple[str, Verdict]])

    def verdict(self, action: str, **_: Any) -> Verdict:
        return Verdict.LIVE if action in ("github.push_branch", "github.open_pr") else Verdict.DRY_RUN

    def record(self, action: str, verdict: Verdict, **_: Any) -> None:
        self.records.append((action, verdict))

    def gated(self, action: str, perform: Callable[[], Any], **_: Any) -> Any:
        self.records.append((action, Verdict.DRY_RUN))

    def ready_pr_allowed(self, repo: str) -> bool:
        return True


@dataclass
class FakeGitHub:
    pushed: list[str] = field(default_factory=list[str])
    prs: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])

    def remote_branch_exists(self, repo: str, branch: str) -> bool:
        return True

    def push(self, worktree: Path, branch: str) -> None:
        self.pushed.append(branch)

    def open_pr(self, repo: str, head: str, base: str, title: str, body: str, draft: bool) -> PullRequest:
        self.prs.append({"title": title, "body": body, "draft": draft, "head": head, "base": base})
        url = f"https://github.com/{repo}/pull/7"
        return PullRequest(number=7, url=url, head=head, base=base, draft=draft, mode="mock")


@dataclass
class FakeDeps:
    run_dir: Path
    agent: ScriptedAgent
    engine: FakeEngine
    gate: FakeGate = field(default_factory=FakeGate)
    github: FakeGitHub = field(default_factory=FakeGitHub)
    agent_type: dict[str, Any] = field(
        default_factory=lambda: {"nodes": {"fix": {"max_turns": 20}}, "validation": {"max_attempts": 1}}
    )
    extra: dict[str, Any] = field(default_factory=dict[str, Any])
    app: None = None
    chat: None = None
    jira: None = None
    vitals_url: str = "http://vitals.invalid"
    bugdrop_url: str = "http://bugdrop.invalid"

    def runner(self, apply_diff: Any = None) -> ScriptedAgent:
        return self.agent


@dataclass
class Toy:
    state: RunState
    sb: FakeSandbox
    deps: FakeDeps

    @property
    def wt(self) -> Path:
        return self.sb.worktree

    def d(self) -> Any:
        return cast(Any, self.deps)


def _state() -> RunState:
    data = json.loads(FIXTURE.read_text())
    data["issue"].update(
        repo="toy",
        gh_repo="acme/toy",
        component=".",
        language="python",
        kind="report",
        title="head(xs, 0) returns an element",
        report={"body": "head([1, 2], 0) should return []"},
        latest_event={},
        last_version="1.0.0",
        base_branch="main",
    )
    for k in ("fix_attempts", "validation", "ship", "pr", "notifications"):
        data.pop(k, None)
    data.update(run_id="r1", status="running", decisions=[], costs={}, timings_ms={})
    state = RunState.model_validate(data)
    state.fix_plan = FixPlan(ladder=["unit"])
    return state


@pytest.fixture
def toy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Toy:
    wt = toy_repo(tmp_path)
    sb = FakeSandbox(wt, wt)

    def sandbox(state: RunState) -> FakeSandbox:
        return sb

    def no_skills(*_: Any, **__: Any) -> tuple[str, list[BaseTool]]:
        return "", []

    monkeypatch.setattr(nodes, "_sandbox", sandbox)
    monkeypatch.setattr(nodes.skills, "for_node", no_skills)
    for flag in ("DA_SECOND_REPRO", "DA_CALL_VARIANTS", "DA_BISECT"):
        monkeypatch.delenv(flag, raising=False)
    agent = ScriptedAgent(
        {
            "reproduce_check": writes("tests/test_check.py", REPRO, test_file="tests/test_check.py"),
            "reproduce": writes("tests/test_repro.py", REPRO, **REPRO_OUT),
            "fix": writes("lib.py", FIXED, **FIX_OUT),
        }
    )
    deps = FakeDeps(tmp_path / "runs" / "r1", agent, FakeEngine({"D16": "open_pr"}))
    return Toy(_state(), sb, deps)


def _apply(state: RunState, update: dict[str, Any]) -> RunState:
    return state.model_copy(update=update)


# ---- fix ------------------------------------------------------------------------------------------------


def test_fix_reproduces_then_fixes(toy: Toy) -> None:
    out = asyncio.run(nodes.fix(toy.state, toy.d()))
    fa: FixAttempt = out["fix_attempts"][-1]
    assert (
        fa.repro_verified and fa.tier == "unit" and fa.repro and fa.repro.test_file == "tests/test_repro.py"
    )
    assert fa.repro_run["exit_code"] != 0 and "FAILED tests/test_repro.py" in fa.repro_run["output_tail"]
    assert toy.deps.agent.feedback["reproduce_unit"] is None and toy.deps.agent.feedback["fix"] is None
    assert fa.files == ["lib.py", "tests/test_repro.py"] and fa.output and fa.output.risk == "low"
    assert (toy.wt / "lib.py").read_text() == FIXED
    assert not list(toy.wt.parent.glob(f"{release.PREFIX}*"))  # every check's checkout is gone


def test_fix_keeps_no_source_written_while_reproducing(toy: Toy) -> None:
    toy.deps.agent.script["reproduce"] = does(
        lambda t: {"r": t["write_file"].invoke({"path": "lib.py", "content": FIXED})},
        writes("tests/test_repro.py", REPRO),
        **REPRO_OUT,
    )
    out = asyncio.run(nodes.fix(toy.state, toy.d()))
    assert out["fix_attempts"][-1].repro_verified  # the source edit was refused or reverted: it still fails


def test_a_test_that_passes_on_the_release_is_no_reproduction(toy: Toy) -> None:
    toy.deps.agent.script["reproduce"] = writes("tests/test_repro.py", PASSING, **REPRO_OUT)
    out = asyncio.run(nodes.fix(toy.state, toy.d()))
    fa: FixAttempt = out["fix_attempts"][-1]
    assert not fa.repro_verified and fa.output is None
    assert "passes on the current (buggy) code" in (toy.deps.agent.feedback["reproduce_unit"] or "")
    assert fa.tiers_tried == [{"tier": "unit", "verified": False, "exit_code": 0}]


def test_a_weakened_reproduction_is_rejected_at_fix_time(toy: Toy) -> None:
    toy.deps.agent.script["fix"] = does(
        writes("lib.py", BROKEN), writes("tests/test_repro.py", WEAK), **FIX_OUT
    )
    asyncio.run(nodes.fix(toy.state, toy.d()))
    problem = toy.deps.agent.feedback["fix"] or ""
    assert "with your source change reverted, the reproduction test no longer reproduces" in problem


def test_a_plan_that_skips_returns_before_any_agent(toy: Toy) -> None:
    toy.state.fix_plan = FixPlan(ladder=["unit"], skip="needs a human: product decision")
    out = asyncio.run(nodes.fix(toy.state, toy.d()))
    assert "fix_attempts" not in out and not toy.deps.agent.feedback


# ---- fix_contract_problem / _run_on_release ---------------------------------------------------------------


def _repro_written(toy: Toy, test: str = REPRO) -> None:
    (toy.wt / "tests" / "test_repro.py").write_text(test)


def _contract(toy: Toy) -> str | None:
    issue = toy.state.issue
    assert issue
    comp = {"test": "python check.py"}
    cmd = "uv run --offline pytest -q tests/test_repro.py"
    return nodes.fix_contract_problem(cast(Any, toy.sb), issue, comp, BASE, cmd, "tests/test_repro.py")


def test_contract_holds_for_a_real_fix(toy: Toy) -> None:
    _repro_written(toy)
    assert _contract(toy) == "you have not changed any source file yet"
    (toy.wt / "lib.py").write_text(FIXED)
    assert _contract(toy) is None
    assert ("checkout", "uv run --offline pytest -q tests/test_repro.py") in toy.sb.log


def test_contract_rejects_a_missing_test_a_non_fix_and_a_broken_suite(toy: Toy) -> None:
    assert _contract(toy) and "is missing" in (_contract(toy) or "")
    _repro_written(toy)
    (toy.wt / "lib.py").write_text(RELEASE.replace("xs[:1]", "xs[:2]"))  # a change that fixes nothing
    assert "still fails with your change" in (_contract(toy) or "")
    (toy.wt / "lib.py").write_text(BROKEN)
    assert "the component suite fails" in (_contract(toy) or "")


def test_run_on_release_keeps_tests_and_drops_the_source_change(toy: Toy) -> None:
    _repro_written(toy)
    (toy.wt / "lib.py").write_text(FIXED)
    seen: dict[str, str] = {}

    def run(rsb: Any) -> CommandResult:
        seen["lib"] = (rsb.worktree / "lib.py").read_text()
        seen["test"] = (rsb.worktree / "tests" / "test_repro.py").read_text()
        seen["root"] = str(rsb.worktree)
        return CommandResult("x", 1, "")

    assert nodes._run_on_release(cast(Any, toy.sb), BASE, run) is not None  # pyright: ignore[reportPrivateUsage]
    assert seen["lib"] == RELEASE and seen["test"] == REPRO and seen["root"] != str(toy.wt)
    assert not Path(seen["root"]).exists() and (toy.wt / "lib.py").read_text() == FIXED


# ---- crash safety (P3-16) ---------------------------------------------------------------------------------


def _fixed_attempt(toy: Toy) -> RunState:
    _repro_written(toy)
    (toy.wt / "lib.py").write_text(FIXED)
    fa = FixAttempt(
        n=1,
        tier="unit",
        repro=ReproOutput.model_validate(REPRO_OUT),
        repro_verified=True,
        repro_run={"command": "uv run --offline pytest -q tests/test_repro.py", "exit_code": 1},
        files=["lib.py", "tests/test_repro.py"],
    )
    return _apply(toy.state, {"fix_attempts": [fa]})


def test_a_crash_mid_check_leaves_the_fix_in_the_worktree(toy: Toy) -> None:
    state = _fixed_attempt(toy)
    toy.sb.crash_in_checkout = True
    with pytest.raises(RuntimeError, match="mid-check"):
        asyncio.run(nodes.validate(state, toy.d()))
    assert (toy.wt / "lib.py").read_text() == FIXED  # not reverted, however the check ended
    assert (toy.wt / "tests" / "test_repro.py").read_text() == REPRO
    # A checkout a killed process left behind is removed by the next check.
    leftover = toy.wt.parent / f"{release.PREFIX}dead"
    git(toy.wt, "worktree", "add", "-q", "--detach", str(leftover), BASE)
    toy.sb.crash_in_checkout = False
    out = asyncio.run(nodes.validate(state, toy.d()))
    assert out["validation"].passed and not leftover.exists()
    assert "release-check-dead" not in git(toy.wt, "worktree", "list")


def test_validate_after_the_fix_was_committed(toy: Toy) -> None:
    """A resumed validate (after pr_and_notify committed, or the diff fixer) proves the same against the tag."""
    state = _fixed_attempt(toy)
    toy.sb.commit("fix(lib): head")
    out = asyncio.run(nodes.validate(state, toy.d()))
    v: Validation = out["validation"]
    assert v.passed and v.failing_before and v.failing_before.exit_code != 0
    assert v.passing_after and v.passing_after.exit_code == 0 and v.suite and v.suite.exit_code == 0
    assert v.changes == {"source": ["lib.py"], "new_test": ["tests/test_repro.py"]} and not v.protected
    assert hostgit.run(toy.wt, "status", "--porcelain").stdout == ""  # validation wrote nothing


# ---- validate: the suite as the release has it (P2-8) -----------------------------------------------------


def test_an_existing_test_edited_to_pass_fails_validation_and_is_flagged(toy: Toy) -> None:
    state = _fixed_attempt(toy)
    (toy.wt / "lib.py").write_text(BROKEN)
    (toy.wt / "tests" / "test_lib.py").write_text("from lib import head\n\nassert head([1, 2], 1) == []\n")
    assert toy.sb.run("python check.py").exit_code == 0  # the worktree's own suite is green
    state.fix_attempts[-1].files.append("tests/test_lib.py")
    out = asyncio.run(nodes.validate(state, toy.d()))
    v: Validation = out["validation"]
    assert not v.passed and v.suite and "FAILED tests/test_lib.py" in v.suite.output_tail
    assert v.protected == ["modified_test: tests/test_lib.py"]
    assert out["validation"].attempts[-1]["protected"] == v.protected


def test_a_harness_change_is_not_part_of_the_proof(toy: Toy) -> None:
    state = _fixed_attempt(toy)
    (toy.wt / "lib.py").write_text(BROKEN)
    (toy.wt / "check.py").write_text("import sys\nsys.exit(0)\n")  # source, but it is what runs the tests
    (toy.wt / "tests" / "conftest.py").write_text("collect_ignore = ['test_lib.py']\n")
    (toy.wt / ".github").mkdir()
    (toy.wt / ".github" / "ci.yml").write_text("on: push\n")
    (toy.wt / "uv.lock").write_text("version = 1\n")
    classes = release.classify_changes(toy.wt, BASE)
    assert classes["harness"] == ["tests/conftest.py"] and classes["ci"] == [".github/ci.yml"]
    assert classes["lockfile"] == ["uv.lock"] and classes["new_test"] == ["tests/test_repro.py"]
    assert release.protected(classes) == [
        "harness: tests/conftest.py",
        "ci: .github/ci.yml",
        "lockfile: uv.lock",
    ]
    out = asyncio.run(nodes.validate(state, toy.d()))
    assert out["validation"].protected and "tests/conftest.py" not in release.proof_paths(classes)


def test_classification() -> None:
    c = release.classify
    assert c("src/lib.ts", "M") == "source" and c("tests/test_x.py", "A") == "new_test"
    assert c("tests/test_x.py", "M") == "modified_test" and c("src/a.test.ts", "D") == "modified_test"
    assert c(".DebugAssist/pipeline.yaml", "M") == "harness" and c("vitest.config.ts", "M") == "harness"
    assert c("gateway/pnpm-lock.yaml", "M") == "lockfile" and c("go.sum", "M") == "lockfile"
    assert c(".github/workflows/ci.yml", "A") == "ci"


def test_validate_without_a_reproduction_or_a_source_change(toy: Toy) -> None:
    fa = FixAttempt(n=1, repro_verified=False, repro_run={"exit_code": 0})
    out = asyncio.run(nodes.validate(_apply(toy.state, {"fix_attempts": [fa]}), toy.d()))
    assert out["validation"].attempts[-1]["result"].startswith("no reproduction test")
    fa = FixAttempt(
        n=1, repro=ReproOutput.model_validate(REPRO_OUT), repro_verified=True, files=["tests/test_repro.py"]
    )
    out = asyncio.run(nodes.validate(_apply(toy.state, {"fix_attempts": [fa]}), toy.d()))
    assert out["validation"].attempts[-1]["result"] == "no source change" and not out["validation"].passed


def test_validate_holds_the_fix_to_a_second_reproduction(toy: Toy, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DA_SECOND_REPRO", "1")
    state = _fixed_attempt(toy)
    out = asyncio.run(nodes.validate(state, toy.d()))
    rec = out["validation"].attempts[-1]["second_reproduction"]
    assert out["validation"].passed and rec["result"] == "passes with the fix"
    assert toy.deps.agent.feedback["reproduce_check"] is None
    assert not (toy.wt / "tests" / "test_check.py").exists()  # a check, never part of the fix
    assert out["costs"]["reproduce_check"] == 0.001


# ---- decide_retry / ship_gate -----------------------------------------------------------------------------


def _validated(toy: Toy) -> RunState:
    state = _fixed_attempt(toy)
    return _apply(state, asyncio.run(nodes.validate(state, toy.d())))


def test_decide_retry(toy: Toy) -> None:
    d = toy.d()
    assert not asyncio.run(nodes.decide_retry(toy.state, d))  # nothing validated yet
    state = _validated(toy)
    assert not asyncio.run(nodes.decide_retry(state, d))  # passed
    assert state.validation
    state.validation.passed = False
    d.agent_type["validation"]["max_attempts"] = 3
    toy.deps.engine.actions["D15"] = "retry"
    assert asyncio.run(nodes.decide_retry(state, d)) and toy.deps.engine.calls[-1] == "D15"
    state.validation.attempts.append({"result": "no source change"})
    assert asyncio.run(nodes.decide_retry(state, d))  # always worth another attempt
    d.agent_type["validation"]["max_attempts"] = 1
    assert not asyncio.run(nodes.decide_retry(state, d))  # the cap


def test_ship_gate(toy: Toy) -> None:
    state = _validated(toy)
    assert asyncio.run(nodes.ship_gate(state, toy.d()))["ship"].outcome == "open_pr"
    assert state.validation
    state.validation.protected = ["modified_test: tests/test_lib.py"]
    assert asyncio.run(nodes.ship_gate(state, toy.d()))["ship"].outcome == "draft_pr"
    state.validation.protected = []
    toy.deps.engine.actions["D16"] = "nonsense"
    assert asyncio.run(nodes.ship_gate(state, toy.d()))["ship"].outcome == "draft_pr"
    assert state.rca and state.rca.output
    state.rca.output.category = "infra"
    state.rca.actionable = False
    ship = asyncio.run(nodes.ship_gate(state, toy.d()))["ship"]
    assert ship.outcome == "rca_only" and "infra" in ship.decision["reason"]
    state.fix_plan = FixPlan(skip="needs a human: product call")
    assert asyncio.run(nodes.ship_gate(state, toy.d()))["ship"].outcome == "escalate"


# ---- pr_and_notify ----------------------------------------------------------------------------------------


def test_pr_and_notify_commits_pushes_and_opens_the_pr(toy: Toy) -> None:
    state = _validated(toy)
    state.fix_attempts[-1].output = None
    state = _apply(state, {"ship": Ship(outcome="open_pr")})
    out = asyncio.run(nodes.pr_and_notify(state, toy.d()))
    pr = toy.deps.github.prs[-1]
    assert out["pr"].number == 7 and not pr["draft"] and pr["head"] == BRANCH and pr["base"] == "main"
    assert toy.deps.github.pushed == [BRANCH] and pr["title"].startswith("fix(")
    msg = git(toy.wt, "log", "-1", "--format=%B")
    assert "Vitals: VIT-1001" in msg and "Jira: SCRUM-6" in msg
    assert git(toy.wt, "show", "--name-only", "--format=", "HEAD").split() == [
        "lib.py",
        "tests/test_repro.py",
    ]
    assert "WARNING" not in pr["body"]
    kinds = [n["kind"] for n in out["notifications"]]
    assert "chat" in kinds and "link" in kinds
    assert ("jira.link", Verdict.DRY_RUN) in toy.deps.gate.records


def test_a_protected_change_at_pr_time_makes_a_flagged_draft(toy: Toy) -> None:
    state = _apply(_validated(toy), {"ship": Ship(outcome="open_pr")})  # an older decision, before the edit
    (toy.wt / "tests" / "test_lib.py").write_text(EXISTING + "\n# reviewed\n")
    out = asyncio.run(nodes.pr_and_notify(state, toy.d()))
    pr = toy.deps.github.prs[-1]
    assert pr["draft"] and out["pr"].draft
    assert "WARNING" in pr["body"] and "modified_test: tests/test_lib.py" in pr["body"]
    assert out["validation"].protected == ["modified_test: tests/test_lib.py"]


def test_rca_only_opens_no_pr(toy: Toy) -> None:
    state = _apply(toy.state, {"ship": Ship(outcome="rca_only")})
    out = asyncio.run(nodes.pr_and_notify(state, toy.d()))
    assert "pr" not in out and not toy.deps.github.prs
    assert out["notifications"][-1]["title"].startswith("rca only")


# ---- the graph --------------------------------------------------------------------------------------------


def _graph_run(toy: Toy, monkeypatch: pytest.MonkeyPatch, category: str = "own_code") -> RunState:
    async def nothing(state: RunState, deps: Any) -> dict[str, Any]:
        return {}

    async def classify(state: RunState, deps: Any) -> dict[str, Any]:
        rca = state.rca
        assert rca and rca.output
        return {
            "rca": rca.model_copy(update={"output": rca.output.model_copy(update={"category": category})})
        }

    for name in ("ingest", "auto_triage", "context_collector", "mitigate"):
        monkeypatch.setattr(nodes, name, nothing)
    monkeypatch.setattr(nodes, "classify_rca", classify)
    app: Any = graph.build_graph(toy.d(), log=lambda _: None).compile(checkpointer=InMemorySaver())  # pyright: ignore[reportUnknownMemberType]
    cfg = {"configurable": {"thread_id": "r1"}, "recursion_limit": 40}
    return RunState.model_validate(asyncio.run(app.ainvoke(toy.state, cfg)))


def test_graph_validated_fix_opens_a_pr(toy: Toy, monkeypatch: pytest.MonkeyPatch) -> None:
    s = _graph_run(toy, monkeypatch)
    assert s.status != "failed", s.errors
    assert s.validation and s.validation.passed and s.ship and s.ship.outcome == "open_pr"
    assert s.pr and not s.pr.draft and s.watch is not None and s.status == "watching"
    assert list(s.timings_ms) == [
        "ingest",
        "auto_triage",
        "context_collector",
        "classify_rca",
        "mitigate",
        "fix",
        "validate",
        "ship_gate",
        "pr_and_notify",
        "post_merge_watch",
    ]
    assert (toy.deps.run_dir / "state.json").is_file()


def test_graph_non_reproducing_test_is_rca_only(toy: Toy, monkeypatch: pytest.MonkeyPatch) -> None:
    toy.deps.agent.script["reproduce"] = writes("tests/test_repro.py", PASSING, **REPRO_OUT)
    s = _graph_run(toy, monkeypatch)
    assert s.ship and s.ship.outcome == "rca_only" and s.pr is None and not toy.deps.github.prs
    assert s.validation and s.validation.attempts[-1]["result"].startswith("no reproduction test")


def test_graph_weakened_test_is_rejected(toy: Toy, monkeypatch: pytest.MonkeyPatch) -> None:
    toy.deps.agent.script["fix"] = does(
        writes("lib.py", BROKEN), writes("tests/test_repro.py", WEAK), **FIX_OUT
    )
    s = _graph_run(toy, monkeypatch)
    assert s.validation and not s.validation.passed
    assert "failing_before_problem" in s.validation.attempts[-1]
    assert s.ship and s.ship.outcome == "draft_pr"  # never a ready PR without the proof
    assert toy.deps.github.prs and toy.deps.github.prs[-1]["draft"]
    assert "Validation did not pass" in toy.deps.github.prs[-1]["body"]


def test_graph_routed_category_is_rca_only(toy: Toy, monkeypatch: pytest.MonkeyPatch) -> None:
    s = _graph_run(toy, monkeypatch, category="infra")
    assert s.ship and s.ship.outcome == "rca_only" and "infra" in s.ship.decision["reason"]
    assert not s.fix_attempts and s.validation is None and not toy.deps.agent.feedback
    assert "fix" not in s.timings_ms and not toy.deps.github.prs


def test_a_resumed_pr_step_neither_fails_nor_double_posts(toy: Toy) -> None:
    """ROADMAP-100 019: a run resumed at pr_and_notify after it committed failed on an empty commit."""
    state = _validated(toy)
    state = _apply(state, {"ship": Ship(outcome="open_pr")})
    asyncio.run(nodes.pr_and_notify(state, toy.d()))
    head = git(toy.wt, "rev-parse", "HEAD")
    out = asyncio.run(nodes.pr_and_notify(state, toy.d()))  # resumed at the same node
    assert git(toy.wt, "rev-parse", "HEAD") == head  # no second commit
    assert out["pr"].number == 7 and toy.deps.github.pushed == [BRANCH, BRANCH]
