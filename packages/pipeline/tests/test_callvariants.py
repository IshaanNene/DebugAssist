"""callvariants: the report's calls re-spelled mechanically, and the check that a fix keeps every spelling working —
on a toy decorator whose narrow fix handles the class call positionally only (as the cachetools#435 fixes did)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from debugassist.integrations.sandbox import CommandResult
from debugassist.pipeline import callvariants as cv
from debugassist.pipeline.nodes import call_variants_check
from debugassist.pipeline.state import Issue

FIXTURE = Path(__file__).parent / "fixtures" / "run_state.json"
SNIPPET = """from lib import deco

class Example:
    @deco
    def value(self, number):
        return number * 2

example = Example()
print(example.value(3))
print(Example.value(example, 3))
"""
REPORT = f"Calling it through the class fails.\n\n```python\n{SNIPPET}```\n"
_HEAD = (
    "class deco:\n    def __init__(self, f):\n        self.f = f\n\n    def __get__(self, obj, cls=None):\n"
)
_BOUND = "        return lambda *a, **k: self.f(obj, *a, **k)\n"
RELEASE = (
    _HEAD + "        if obj is None:\n            return lambda *a, **k: self.f(None, *a, **k)\n" + _BOUND
)
NARROW = (
    _HEAD
    + "        if obj is None:\n            return lambda inst, *a, **k: self.f(inst, *a, **k)\n"
    + _BOUND
)
WIDE = _HEAD + "        if obj is None:\n            return self.f\n" + _BOUND


class FakeSandbox:
    def __init__(self, worktree: Path) -> None:
        self.worktree = worktree

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


def _issue(report: str = REPORT, language: str = "python") -> Issue:
    data = json.loads(FIXTURE.read_text())["issue"]
    data.update(repo="toy", component=".", language=language, report={"body": report}, about=None)
    return Issue.model_validate(data)


def _check(tmp_path: Path, lib: str, **kw: Any) -> dict[str, Any]:
    (tmp_path / "lib.py").write_text(lib)
    return call_variants_check(cast(Any, FakeSandbox(tmp_path)), _issue(**kw), {"test": "python -m pytest"})


def test_variants_respell_each_call_with_the_same_binding() -> None:
    [code] = cv.snippets(REPORT)
    by_call = {base.call: [o.call for o in others] for base, others in cv.variants(code)}
    assert set(by_call) == {"example.value(3)", "Example.value(example, 3)"}
    assert "Example.value(self=example, number=3)" in by_call["Example.value(example, 3)"]
    assert "example.value(number=3)" in by_call["Example.value(example, 3)"]
    assert "Example.value(example, 3)" in by_call["example.value(3)"]


def test_a_narrow_fix_fails_on_the_keyword_spelling(tmp_path: Path) -> None:
    rec = _check(tmp_path, NARROW)
    assert rec["result"] == "fail"
    assert any("Example.value(self=example, number=3)" in m and "TypeError" in m for m in rec["mismatches"])
    assert not (tmp_path / ".debugassist_variant.py").exists()


def test_a_wide_fix_passes_every_spelling(tmp_path: Path) -> None:
    rec = _check(tmp_path, WIDE)
    assert rec["result"] == "pass" and rec["checked"] >= 6 and rec["mismatches"] == []


def test_the_release_only_checks_the_reported_calls_that_work(tmp_path: Path) -> None:
    # on the release only `example.value(3)` works; its class spellings fail — the bug itself
    rec = _check(tmp_path, RELEASE)
    assert rec["result"] == "fail"
    assert all(m.split("`")[3] == "example.value(3)" for m in rec["mismatches"])


def test_nothing_to_respell_is_unchecked(tmp_path: Path) -> None:
    assert _check(tmp_path, WIDE, report="It breaks when I click save.")["result"] == "unchecked"
    assert _check(tmp_path, WIDE, language="typescript")["result"] == "unchecked"
