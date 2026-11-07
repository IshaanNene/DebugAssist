"""`make doctor` fails when the repo sits in a synced folder or the disk is nearly full (docs/LESSONS.md)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from debugassist.core.policy import ROOT


def doctor() -> ModuleType:
    spec = importlib.util.spec_from_file_location("doctor", ROOT / "scripts" / "doctor.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_repo_under_a_synced_folder_is_found() -> None:
    d = doctor()

    def none(_: Path) -> set[str]:
        return set()

    def icloud_desktop(p: Path) -> set[str]:
        return {d.FILE_PROVIDER_XATTR} if p == Path("/Users/me/Desktop") else set()

    assert d.synced_folder(Path("/Users/me/src/DebugAssist"), none) is None
    assert "iCloud" in d.synced_folder(Path("/Users/me/Desktop/DebugAssist"), icloud_desktop)
    assert d.synced_folder(Path("/Users/me/Library/CloudStorage/Dropbox/DebugAssist"), none)
    assert d.synced_folder(Path("/Users/me/Dropbox/code/DebugAssist"), none)
    assert d.synced_folder(Path("/Users/me/Library/Mobile Documents/com~apple~CloudDocs/x"), none)


def test_disk_share_matches_df() -> None:
    d = doctor()
    gib = 2**30
    assert round(d.disk_used(460 * gib, 391 * gib, 44 * gib), 2) == 0.90  # this machine on 2026-11-07
    assert d.disk_used(100, 50, 50) == 0.5
    assert d.disk_used(0, 0, 0) == 0.0
