"""bisect.prove: the reproduction test run back through history — on a toy repo with release tags, a commit that
introduces the bug, a commit where the test cannot run, and an untracked dependency directory that must survive."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

from debugassist.pipeline import bisect

TEST = "tests/test_repro.py"
REPRO = "from lib import half\n\nassert half(3) == 1.5, half(3)\n"


def _git(wt: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=wt, capture_output=True, text=True
    )
    return out.stdout.strip()


def _commit(wt: Path, lib: str, msg: str, tag: str | None = None) -> str:
    (wt / "lib.py").write_text(lib)
    _git(wt, "add", "lib.py")
    _git(wt, "commit", "-qm", msg)
    if tag:
        _git(wt, "tag", tag)
    return _git(wt, "rev-parse", "HEAD")


def _repo(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    wt = tmp_path / "toy"
    wt.mkdir()
    _git(wt, "init", "-q")
    shas = {
        "v1": _commit(wt, "def half(x):\n    return x / 2\n", "half", tag="v1.0.0"),
        "docs": _commit(wt, "def half(x):\n    '''Half of x.'''\n    return x / 2\n", "docs"),
        "culprit": _commit(wt, "def half(x):\n    '''Half of x.'''\n    return x // 2\n", "faster half"),
        "broken": _commit(wt, "def half(x)\n    return x // 2\n", "wip: syntax error"),  # test cannot run
        "later": _commit(
            wt, "def half(x):\n    '''Half of x, floored.'''\n    return x // 2\n", "doc", tag="v1.1.0"
        ),
    }
    (wt / ".venv").mkdir()
    (wt / ".venv" / "keep").write_text("installed")  # untracked and NOT ignored: must survive
    return wt, shas


def _run(wt: Path):
    def run(command: str) -> tuple[int, str]:
        p = subprocess.run(
            [sys.executable, command.split()[-1]],
            cwd=wt,
            capture_output=True,
            text=True,
            env={"PYTHONPATH": str(wt)},
        )
        return p.returncode, p.stdout + p.stderr

    return run


def unrelated(code: int, output: str) -> bool:
    return "SyntaxError" in output


def test_finds_the_commit_that_introduced_the_bug_and_restores_the_worktree(tmp_path: Path) -> None:
    wt, shas = _repo(tmp_path)
    (wt / "lib.py").write_text("def half(x):\n    return x / 2\n")  # the fix, uncommitted
    (wt / "tests").mkdir()
    (wt / TEST).write_text(REPRO)  # the reproduction, untracked
    res = bisect.prove(wt, "v1.1.0", TEST, f"python {TEST}", unrelated, _run(wt))
    assert res["result"] == "found", res
    assert res["first_bad"] == shas["culprit"][:10] and res["subject"] == "faster half"
    assert res["good"] == "v1.0.0" and res["tags_tried"] == [{"tag": "v1.0.0", "verdict": "good"}]
    # as it was: same HEAD, the fix and the test back, the untracked directory untouched, no bisect left running
    assert _git(wt, "rev-parse", "HEAD") == shas["later"]
    assert (wt / "lib.py").read_text() == "def half(x):\n    return x / 2\n"
    assert (wt / TEST).read_text() == REPRO
    assert (wt / ".venv" / "keep").read_text() == "installed"
    assert not (wt / ".git" / "BISECT_LOG").exists()


def test_a_bug_present_in_every_earlier_release_is_not_a_regression(tmp_path: Path) -> None:
    wt = tmp_path / "toy"
    wt.mkdir()
    _git(wt, "init", "-q")
    _commit(wt, "def half(x):\n    return x // 2\n", "half", tag="v1.0.0")
    _commit(wt, "def half(x):\n    '''x // 2'''\n    return x // 2\n", "doc", tag="v1.1.0")
    (wt / "tests").mkdir()
    (wt / TEST).write_text(REPRO)
    res = bisect.prove(wt, "v1.1.0", TEST, f"python {TEST}", unrelated, _run(wt))
    assert res["result"] == "no_good_release" and (wt / TEST).exists()


def test_agrees_with_the_rcas_suspect_by_prefix() -> None:
    found = {"result": "found", "first_bad": "57d2e48abc"}
    assert bisect.agrees(found, "57d2e48") is True
    assert bisect.agrees(found, "0985ec0") is False
    assert bisect.agrees(found, None) is None


def test_an_untestable_commit_next_to_the_change_narrows_to_candidates(tmp_path: Path) -> None:
    wt = tmp_path / "toy"
    wt.mkdir()
    _git(wt, "init", "-q")
    _commit(wt, "def half(x):\n    return x / 2\n", "half", tag="v1.0.0")
    broken = _commit(wt, "def half(x)\n    return x / 2\n", "wip: syntax error")
    culprit = _commit(wt, "def half(x):\n    return x // 2\n", "faster half")
    _commit(wt, "def half(x):\n    # floored\n    return x // 2\n", "doc", tag="v1.1.0")
    (wt / "tests").mkdir()
    (wt / TEST).write_text(REPRO)
    res = bisect.prove(wt, "v1.1.0", TEST, f"python {TEST}", unrelated, _run(wt))
    assert res["result"] == "narrowed" and set(res["candidates"]) == {broken[:10], culprit[:10]}
    assert not (wt / ".git" / "BISECT_LOG").exists()


def test_a_failure_of_another_kind_on_an_old_commit_is_skipped_not_blamed(tmp_path: Path) -> None:
    # before `half` existed the test fails with ImportError: that commit cannot be the culprit's evidence
    wt = tmp_path / "toy"
    wt.mkdir()
    _git(wt, "init", "-q")
    _commit(wt, "def double(x):\n    return x * 2\n", "double", tag="v0.9.0")
    _commit(
        wt, "def double(x):\n    return x * 2\n\n\ndef half(x):\n    return x / 2\n", "half", tag="v1.0.0"
    )
    culprit = _commit(wt, "def double(x):\n    return x * 2\n\n\ndef half(x):\n    return x // 2\n", "faster")
    _commit(
        wt,
        "def double(x):\n    return x * 2\n\n\ndef half(x):\n    return x // 2  # ok\n",
        "doc",
        tag="v1.1.0",
    )
    (wt / "tests").mkdir()
    (wt / TEST).write_text(REPRO)
    res = bisect.prove(wt, "v1.1.0", TEST, f"python {TEST}", unrelated, _run(wt))
    assert res["result"] == "found" and res["first_bad"] == culprit[:10]
    assert res["release_failure"] == ["AssertionError"]
    assert bisect.exceptions("ImportError: cannot import name 'half'") == {"ImportError"}


def test_a_test_that_asserts_more_than_the_old_behaviour_is_bisected_by_case(tmp_path: Path) -> None:
    # the file fails on every release (its second case asserts a new requirement); its first case alone bisects
    wt, shas = _repo(tmp_path)
    (wt / "tests").mkdir()
    (wt / TEST).write_text(
        "from lib import half\n\n\ndef test_old_behaviour():\n    assert half(3) == 1.5\n\n\n"
        "def test_new_requirement():\n    assert half(None) == 0\n"
    )

    def run(command: str) -> tuple[int, str]:
        p = subprocess.run(
            [sys.executable, *shlex.split(command)[1:]],
            cwd=wt,
            capture_output=True,
            text=True,
            env={"PYTHONPATH": str(wt), "PATH": os.environ["PATH"]},
        )
        return p.returncode, p.stdout + p.stderr

    cmd = f"python -m pytest -q -p no:cacheprovider {TEST}"
    whole = bisect.prove(wt, "v1.1.0", TEST, cmd, unrelated, run)
    assert whole["result"] == "no_good_release"
    res = bisect.prove_by_case(wt, "v1.1.0", TEST, cmd, bisect.pytest_case_command(cmd, TEST), unrelated, run)
    assert res["result"] == "found" and res["first_bad"] == shas["culprit"][:10]
    assert res["case"] == f"{TEST}::test_old_behaviour" and res["whole_file"] == "no_good_release"
