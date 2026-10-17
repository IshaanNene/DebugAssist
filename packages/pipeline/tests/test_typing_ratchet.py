"""ROADMAP-100 035: loose typing in `pipeline/` may only shrink.

Strict pyright passes, but `dict[str, Any]` records and `pyright: ignore` comments are where it protects nothing.
The counts below are today's; a change that adds one fails here, and a change that removes some should lower
the number in the same commit (the test says so)."""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).parents[1] / "src" / "debugassist" / "pipeline"
CEILING = {"dict[str, Any]": 233, "pyright: ignore": 9}


def counts() -> dict[str, int]:
    text = "".join(p.read_text() for p in sorted(SRC.glob("*.py")))
    return {k: len(re.findall(re.escape(k), text)) for k in CEILING}


def test_loose_typing_does_not_grow() -> None:
    now = counts()
    grew = {k: f"{now[k]} > {CEILING[k]}" for k in CEILING if now[k] > CEILING[k]}
    assert not grew, f"more loose typing in pipeline/: {grew}; use a typed model instead"


def test_the_ceiling_follows_improvements() -> None:
    now = counts()
    fell = {k: now[k] for k in CEILING if now[k] < CEILING[k]}
    assert not fell, f"loose typing fell to {fell}: lower CEILING in this file to lock the gain in"
