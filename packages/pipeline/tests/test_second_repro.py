"""DA_SECOND_REPRO: the independent check runs on the release without the fix or the fixing agent's tests, and
holds the fix to a second reproduction — on a throwaway git repo with a scripted checker."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from debugassist.integrations.sandbox import CommandResult
from debugassist.llm.spec import LLMResult
from debugassist.pipeline.nodes import second_reproduction
from debugassist.pipeline.state import RunState

FIXTURE = Path(__file__).parent / "fixtures" / "run_state.json"
RELEASE = "def head(xs, n=1):\n    return xs[:n] if n > 0 else xs[:1]\n"
NARROW = "def head(xs, n=1):\n    if n == 0:\n        return []\n    return xs[:n] if n > 0 else xs[:1]\n"
WIDE = "def head(xs, n=1):\n    return xs[: max(n, 0)]\n"
FIRST = "from lib import head\n\nassert head([1, 2], 0) == []\n"
SECOND = "from lib import head\n\nassert head([1, 2], 0) == []\nassert head([1, 2], -1) == []\n"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout


class FakeSandbox:
    """Runs `… <test file>` as a plain Python script in the worktree (exit code = test result)."""

    def __init__(self, worktree: Path, checkouts: list[Path] | None = None) -> None:
        self.worktree = worktree
        self.checkouts = [] if checkouts is None else checkouts

    def checkout(self, root: Path) -> FakeSandbox:
        self.checkouts.append(root)
        return FakeSandbox(root, self.checkouts)

    def run(
        self, command: str, *, workdir: str = ".", network: bool = False, timeout: int = 600
    ) -> CommandResult:
        p = subprocess.run(
            [sys.executable, command.split()[-1]],
            cwd=self.worktree,
            capture_output=True,
            text=True,
            env={"PYTHONPATH": str(self.worktree)},
        )
        return CommandResult(command=command, exit_code=p.returncode, output=p.stdout + p.stderr)

    def diff(self, base: str = "HEAD") -> str:
        _git(self.worktree, "add", "-A", "--intent-to-add", ".")
        return _git(self.worktree, "diff", base, "--", ".")


class Checker:
    """A scripted second-reproduction agent; records what it could see."""

    def __init__(self, sb: FakeSandbox, test: str, name: str = "tests/test_check.py") -> None:
        self.sb, self.test, self.name = sb, test, name
        self.saw: dict[str, Any] = {}
        self.feedback: str | None = None

    def __call__(self, apply_diff: Any = None) -> Checker:
        return self

    async def run(self, spec: Any, prompt: str, schema: Any, **kw: Any) -> LLMResult:
        wt = self.sb.checkouts[-1]  # where the checker works: a checkout of the release
        self.saw = {
            "lib": (wt / "lib.py").read_text(),
            "first_test": (wt / "tests" / "test_repro.py").exists(),
            "prompt": prompt,
        }
        tools = {t.name: t for t in kw["tools"]}
        tools["write_file"].invoke({"path": self.name, "content": self.test})
        kw["diff_fn"]()  # as the real runner does: marks new files intent-to-add
        out = {"test_file": self.name, "asserts": "head returns [] for n <= 0", "failure": "AssertionError"}
        self.feedback = kw["validate_output"](out)
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


def _setup(tmp_path: Path, fix: str, second: str) -> tuple[RunState, Any, FakeSandbox, Checker]:
    wt = tmp_path / "toy"
    wt.mkdir()
    (wt / "lib.py").write_text(RELEASE)
    _git(wt, "init", "-q")
    _git(wt, "-c", "user.name=t", "-c", "user.email=t@t", "add", ".")
    _git(wt, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "release")
    _git(wt, "tag", "v1.0.0")
    (wt / "lib.py").write_text(fix)
    (wt / "tests").mkdir()
    (wt / "tests" / "test_repro.py").write_text(FIRST)
    FakeSandbox(wt).diff("v1.0.0")  # the fix step's own diffs leave its new test intent-to-add
    data = json.loads(FIXTURE.read_text())
    data["issue"].update(
        repo="toy",
        component=".",
        language="python",
        kind="report",
        title="head(xs, 0) returns an element",
        report={"body": "head([1, 2], 0) should return []"},
        latest_event={},
        about=None,
        last_version="1.0.0",
    )
    state = RunState.model_validate(data)
    sb = FakeSandbox(wt)
    checker = Checker(sb, second)
    deps = cast(Any, type("D", (), {"agent_type": {"nodes": {"fix": {"max_turns": 20}}}, "extra": {}})())
    deps.runner = checker
    return state, deps, sb, checker


def _run(state: RunState, deps: Any, sb: FakeSandbox) -> tuple[Any, dict[str, Any], float]:
    comp = {"test": "python -m pytest", "test_file_glob": "tests/test_*.py"}
    return asyncio.run(second_reproduction(state, deps, cast(Any, sb), comp, "v1.0.0"))


def test_checker_sees_the_release_only_and_catches_a_narrow_fix(tmp_path: Path) -> None:
    state, deps, sb, checker = _setup(tmp_path, NARROW, SECOND)
    run, rec, cost = _run(state, deps, sb)
    assert checker.saw["lib"] == RELEASE and not checker.saw["first_test"]
    assert "head([1, 2], 0) should return []" in checker.saw["prompt"]
    assert checker.feedback is None  # its test fails on the release
    assert run is not None and run.exit_code != 0 and rec["result"] == "fails with the fix"
    assert cost == 0.001 and "head([1, 2], -1)" in rec["test_source"]
    # the worktree is as it was: the fix applied, the first test back, the check gone
    wt = sb.worktree
    assert (wt / "lib.py").read_text() == NARROW
    assert (wt / "tests" / "test_repro.py").read_text() == FIRST
    assert not (wt / "tests" / "test_check.py").exists()


def test_a_wide_fix_passes(tmp_path: Path) -> None:
    state, deps, sb, _ = _setup(tmp_path, WIDE, SECOND)
    run, rec, _ = _run(state, deps, sb)
    assert run is not None and run.exit_code == 0 and rec["result"] == "passes with the fix"
    assert (sb.worktree / "lib.py").read_text() == WIDE


def test_a_second_test_that_passes_on_the_release_checks_nothing(tmp_path: Path) -> None:
    state, deps, sb, checker = _setup(
        tmp_path, NARROW, "from lib import head\n\nassert head([1], 1) == [1]\n"
    )
    run, rec, _ = _run(state, deps, sb)
    assert checker.feedback and "passes on the current" in checker.feedback
    assert run is None and rec["result"].startswith("the second test does not reproduce")
    assert (sb.worktree / "lib.py").read_text() == NARROW
    assert not (sb.worktree / "tests" / "test_check.py").exists()


def test_the_fixing_agents_test_name_is_refused(tmp_path: Path) -> None:
    state, deps, sb, checker = _setup(tmp_path, NARROW, SECOND)
    checker.name = "tests/test_repro.py"
    _run(state, deps, sb)
    assert checker.feedback and "already taken" in checker.feedback
    assert (sb.worktree / "tests" / "test_repro.py").read_text() == FIRST


def test_callers_mode_shows_the_checker_the_codes_other_uses(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("DA_SECOND_REPRO", "callers")
    state, deps, sb, checker = _setup(tmp_path, NARROW, SECOND)
    assert state.rca and state.rca.output
    state.rca.output.location.file, state.rca.output.location.function = "lib.py", "head"
    (sb.worktree / "README.md").write_text("Usage:\n\n    head(items, n=-1)  # nothing\n")
    _git(sb.worktree, "add", "README.md")  # part of the release: the checker works on the release
    _git(sb.worktree, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "docs", "--", "README.md")
    _git(sb.worktree, "tag", "-f", "v1.0.0")
    _, rec, _ = _run(state, deps, sb)
    assert "head(items, n=-1)" in checker.saw["prompt"] and "repository usages" in checker.saw["prompt"]
    assert rec["usages"]["names"][0] == "head"


def test_report_mode_shows_no_usages(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("DA_SECOND_REPRO", "1")
    state, deps, sb, checker = _setup(tmp_path, NARROW, SECOND)
    _run(state, deps, sb)
    assert "repository usages" not in checker.saw["prompt"]
