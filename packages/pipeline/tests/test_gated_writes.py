"""ROADMAP-100 030: every external write in the pipeline is decided by the policy gate.

A static scan: each function that calls a write method of an external client (Jira, GitHub, the App, chat) or
POSTs to a source service must also ask the gate (`verdict`, `gated`, or `gated_write`). A new write without the
gate fails here before it can reach anyone's repository or tracker."""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).parents[1] / "src" / "debugassist" / "pipeline"
CLIENTS = {"jira", "github", "chat", "app"}
WRITES = {"create", "comment", "transition", "link", "push", "open_pr", "send", "set_draft"}
ASKS = {"verdict", "gated", "gated_write"}
# Thin delegation, not a decision: the router forwards to the client chosen per repository.
DELEGATES = {("deps.py", "push"), ("deps.py", "open_pr")}


def _is_write(call: ast.Call) -> bool:
    f = call.func
    if not isinstance(f, ast.Attribute):
        return False
    if f.attr == "post" and isinstance(f.value, ast.Name) and f.value.id == "httpx":
        return True
    if f.attr not in WRITES:
        return False
    owner = f.value
    return (isinstance(owner, ast.Attribute) and owner.attr in CLIENTS) or (
        isinstance(owner, ast.Name) and owner.id in {"a", "app"}
    )


def _asks(fn: ast.AST) -> bool:
    return any(
        (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ASKS)
        or (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ASKS)
        for n in ast.walk(fn)
    )


def ungated() -> list[str]:
    out: list[str] = []
    for path in sorted(SRC.glob("*.py")):
        tree = ast.parse(path.read_text())
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if (path.name, fn.name) in DELEGATES:
                continue
            writes = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and _is_write(n)]
            if writes and not _asks(fn):
                out += [f"{path.name}:{w.lineno} {fn.name}" for w in writes]
    return out


def test_no_external_write_skips_the_gate() -> None:
    assert ungated() == []


def test_the_scan_finds_a_write_without_the_gate(tmp_path: Path) -> None:
    bad = ast.parse("def f(deps):\n    deps.jira.comment('K-1', [])\n")
    ok = ast.parse(
        "def f(deps):\n    if deps.gate.verdict('jira.comment'):\n        deps.jira.comment('K-1', [])\n"
    )
    calls = [n for n in ast.walk(bad) if isinstance(n, ast.Call) and _is_write(n)]
    assert calls and not _asks(bad.body[0]) and _asks(ok.body[0])
