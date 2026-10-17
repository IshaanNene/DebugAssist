"""Roadmap 068: run state is written atomically, so a reader never sees half a file."""

from __future__ import annotations

from pathlib import Path

import pytest

from debugassist.core.files import write_atomic


def test_a_failed_write_leaves_the_old_file_and_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "run" / "state.json"
    write_atomic(target, '{"v": 1}')
    assert target.read_text() == '{"v": 1}'

    def boom(*_: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", boom)
    with pytest.raises(OSError, match="disk full"):
        write_atomic(target, '{"v": 2}')
    assert target.read_text() == '{"v": 1}'
    assert [p.name for p in target.parent.iterdir()] == ["state.json"]
