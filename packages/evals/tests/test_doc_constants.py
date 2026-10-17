"""ROADMAP-100 092: a limit the docs state next to its constant's name is the limit the code has.

Docs cite a constant as `` `NAME` = value `` (e.g. `MODEL_CALL_TIMEOUT_S` = 180); this test finds every such
citation in the docs and the README and compares it with the constant. LESSONS once said 300 s where the code
said 180 (audit P3-21)."""

from __future__ import annotations

import importlib
import re
from pathlib import Path

ROOT = Path(__file__).parents[3]
CITE = re.compile(r"`([A-Z][A-Z0-9_]+)` = ([0-9][0-9_.]*)")
WHERE = {  # constant → the module that defines it
    "MODEL_CALL_TIMEOUT_S": "debugassist.llm.runner",
    "RETRY_BASE": "debugassist.pipeline.app_cli",
    "MAX_ATTEMPTS": "debugassist.pipeline.app_cli",
    "REPOS_TTL": "debugassist.integrations.github_app",
    "MAX_RESULT_CHARS": "debugassist.mcp_servers.common",
}


def citations() -> list[tuple[str, str, float]]:
    out: list[tuple[str, str, float]] = []
    for f in [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]:
        for name, value in CITE.findall(f.read_text()):
            out.append((f.name, name, float(value.replace("_", ""))))
    return out


def test_every_cited_constant_matches_the_code() -> None:
    found = citations()
    assert found, "no `NAME` = value citations found"
    wrong: list[str] = []
    for doc, name, value in found:
        assert name in WHERE, f"{doc} cites {name}: add where it is defined to WHERE"
        actual = float(getattr(importlib.import_module(WHERE[name]), name))
        if actual != value:
            wrong.append(f"{doc}: {name} = {value:g}, code has {actual:g}")
    assert not wrong, wrong
