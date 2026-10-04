from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from debugassist.mcp_servers import git_history as gh


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    r = tmp_path / "app"
    r.mkdir()
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=r, check=True)

    def commit(path: str, text: str, msg: str, tag: str | None = None) -> None:
        (r / path).parent.mkdir(parents=True, exist_ok=True)
        (r / path).write_text(text)
        subprocess.run(["git", "add", "."], cwd=r, check=True)
        subprocess.run([*git, "commit", "-qm", msg], cwd=r, check=True)
        if tag:
            subprocess.run([*git, "tag", tag], cwd=r, check=True)

    commit("src/router.ts", "await whenHydrated();\n", "feat: router", "v1.5.0")
    commit("README.md", "docs\n", "docs: readme")
    commit("src/router.ts", "// fast path\n", "perf(notifications): skip hydration wait", "v1.6.0")
    monkeypatch.setenv("CODE_REPOS", json.dumps({"app": str(r)}))
    return r


def test_previous_release_and_window(repo: Path) -> None:
    assert gh.previous_release("app", "v1.6.0")["previous_release"] == "v1.5.0"
    commits = gh.commits_between("app", "v1.5.0", "v1.6.0", None)
    assert commits["commits"][0]["subject"].startswith("perf(notifications)")


def test_bisect_ranks_commits_touching_stack_files(repo: Path) -> None:
    cands = gh.bisect_candidates("app", "v1.5.0", "v1.6.0", ["src/router.ts"])
    assert cands["candidates"][0]["subject"].startswith("perf(notifications)")


def test_refs_are_validated(repo: Path) -> None:
    with pytest.raises(ValueError):
        gh.diff_stats("app", "v1.5.0;rm -rf /", "v1.6.0")
    with pytest.raises(ValueError):
        gh.previous_release("unknown-repo", "v1.6.0")
