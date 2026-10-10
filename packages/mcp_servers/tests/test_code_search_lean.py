from __future__ import annotations

import json
from pathlib import Path

import pytest

from debugassist.mcp_servers import code_search


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "src").mkdir()
    lines = [f"def f{i}():" if i % 100 == 0 else f"    x{i} = {i}" for i in range(1, 251)]
    (tmp_path / "src" / "eta.py").write_text("\n".join(lines) + "\n")
    monkeypatch.setenv("CODE_REPOS", json.dumps({"svc": str(tmp_path)}))
    return tmp_path


def test_full_read_is_unchanged(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DA_CONTEXT", raising=False)
    out = code_search.read_file("svc", "src/eta.py")
    assert out["end_line"] == 250 and "more" not in out


def test_lean_read_is_a_window_with_an_outline(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DA_CONTEXT", "lean")
    out = code_search.read_file("svc", "src/eta.py")
    assert out["end_line"] == 120 and out["total_lines"] == 250 and "outline_file" in out["more"]
    assert code_search.read_file("svc", "src/eta.py", 190, 210)["end_line"] == 210
    assert code_search.read_file("svc", "src/eta.py", 1, 240)["end_line"] == 120
    o = code_search.outline_file("svc", "src/eta.py")
    assert "  200  def f200()" in o["outline"] and o["evidence_id"]
