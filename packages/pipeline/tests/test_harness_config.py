"""Validation reads the repository's harness config from the release under test, never from the worktree the
fix agent edits (audit P2-8): a `test: "true"` there must not make "the suite passes" true."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from debugassist.pipeline import nodes
from debugassist.pipeline.state import RunState

FIXTURE = Path(__file__).parent / "fixtures" / "run_state.json"
CFG = "version: 1\ncomponents:\n  .:\n    path: .\n    language: python\n    test: pytest -q\n"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True, capture_output=True
    )


@pytest.fixture
def state(tmp_path: Path) -> RunState:
    (tmp_path / ".DebugAssist").mkdir()
    (tmp_path / ".DebugAssist" / "pipeline.yaml").write_text(CFG)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "init")
    _git(tmp_path, "tag", "v1.0.0")
    s = RunState.model_validate(json.loads(FIXTURE.read_text()))
    assert s.issue
    s.issue.last_version, s.issue.component = "1.0.0", "."
    return s


def test_an_edited_pipeline_yaml_is_ignored(tmp_path: Path, state: RunState) -> None:
    (tmp_path / ".DebugAssist" / "pipeline.yaml").write_text(CFG.replace("pytest -q", "true"))
    assert nodes.component_cfg(state, tmp_path)["test"] == "pytest -q"


def test_a_release_without_a_harness_config_is_an_error(tmp_path: Path, state: RunState) -> None:
    _git(tmp_path, "rm", "-q", ".DebugAssist/pipeline.yaml")
    _git(tmp_path, "commit", "-qm", "drop")
    _git(tmp_path, "tag", "-f", "v1.0.0")
    (tmp_path / ".DebugAssist").mkdir(exist_ok=True)
    (tmp_path / ".DebugAssist" / "pipeline.yaml").write_text(CFG.replace("pytest -q", "true"))
    with pytest.raises(RuntimeError, match=r"no \.DebugAssist/pipeline\.yaml"):
        nodes.component_cfg(state, tmp_path)


def test_a_renamed_or_quoted_source_file_is_reverted_too(tmp_path: Path) -> None:
    """Audit P3-22: `git status --porcelain` was sliced per line, so renames and quoted paths survived."""
    from types import SimpleNamespace
    from typing import Any, cast

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "lib.py").write_text("x = 1\n")
    (tmp_path / "src" / "odd name é.py").write_text("y = 1\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "init")
    _git(tmp_path, "mv", "src/lib.py", "src/moved.py")
    (tmp_path / "src" / "odd name é.py").write_text("y = 2\n")
    (tmp_path / "src" / "new.py").write_text("z = 1\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_new.py").write_text("def test_x(): ...\n")
    sb = cast(Any, SimpleNamespace(worktree=tmp_path))
    nodes._revert_non_tests(sb)  # pyright: ignore[reportPrivateUsage]
    assert (tmp_path / "src" / "lib.py").read_text() == "x = 1\n"
    assert not (tmp_path / "src" / "moved.py").exists() and not (tmp_path / "src" / "new.py").exists()
    assert (tmp_path / "src" / "odd name é.py").read_text() == "y = 1\n"
    assert (tmp_path / "tests" / "test_new.py").exists()  # tests are kept
    assert nodes._new_test_files(sb) == ["tests/test_new.py"]  # pyright: ignore[reportPrivateUsage]


def test_commit_trailers_name_the_issue_source() -> None:
    s = RunState.model_validate(json.loads(FIXTURE.read_text()))
    assert s.issue
    assert nodes._commit_trailer(s.issue) == f"Vitals: {s.issue.id}"  # pyright: ignore[reportPrivateUsage]
    s.issue.app_issue, s.issue.url = 5, "https://github.com/acme/widgets/issues/5"
    assert nodes._commit_trailer(s.issue) == "Fixes: https://github.com/acme/widgets/issues/5"  # pyright: ignore[reportPrivateUsage]


def test_a_new_test_or_source_change_that_skips_tests_is_flagged(tmp_path: Path) -> None:
    """ROADMAP-100 016: a skip marker in a new test or the source change can hide a failing case."""
    from debugassist.pipeline import release

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "lib.py").write_text("def f():\n    return 1\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "init")
    _git(tmp_path, "tag", "v1")
    (tmp_path / "src" / "lib.py").write_text(
        "import pytest\n\ndef f():\n    pytest.skip('flaky')\n    return 2\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_new.py").write_text(
        "import pytest\n\n@pytest.mark.xfail\ndef test_f(): ...\n"
    )
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\naddopts = '-k not slow'\n")
    classes = release.classify_changes(tmp_path, "v1")
    flagged = release.flagged(tmp_path, "v1", classes)
    assert "harness: pyproject.toml" in flagged
    assert any(f.startswith("skips_tests: src/lib.py") for f in flagged)
    assert any(f.startswith("skips_tests: tests/test_new.py") and "xfail" in f for f in flagged)
