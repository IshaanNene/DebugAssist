"""A file's outline: its symbols with line numbers, so an agent can read only the range it needs.

The context audit (`debugassist eval context`) found `read_file` results are the largest share of agents'
input tokens — reads of ~180 lines, re-sent on every later turn. An outline costs a few dozen tokens and turns
"read the whole file" into "read lines 96–118". Regex-based and dependency-free on purpose: TypeScript /
JavaScript, Python and Go cover the MiniRide repos; anything else falls back to top-level declarations.
"""

from __future__ import annotations

import re

_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "ts": [
        re.compile(
            r"^\s*(export\s+)?(default\s+)?(async\s+)?(function\*?|class|interface|type|enum)\s+([A-Za-z_$][\w$]*)"
        ),
        re.compile(
            r"^\s*(export\s+)?(const|let)\s+([A-Za-z_$][\w$]*)\s*(:[^=]+)?=\s*(async\s*)?(\([^)]*\)\s*(:[^=]+)?=>|[A-Za-z_$][\w$]*\s*=>|function)"
        ),
        re.compile(r"^\s{2,}(async\s+)?([A-Za-z_$][\w$]*)\s*\([^;]*\)\s*(:[^{]+)?\{\s*$"),  # methods
    ],
    "py": [re.compile(r"^(\s*)(async\s+def|def|class)\s+([A-Za-z_]\w*)")],
    "go": [
        re.compile(r"^func\s+(\([^)]*\)\s*)?([A-Za-z_]\w*)"),
        re.compile(r"^type\s+([A-Za-z_]\w*)\s+(struct|interface)"),
    ],
}
_EXT = {".ts": "ts", ".tsx": "ts", ".js": "ts", ".jsx": "ts", ".mjs": "ts", ".py": "py", ".go": "go"}
_KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "function", "else", "do", "try"}


def language(path: str) -> str | None:
    for ext, lang in _EXT.items():
        if path.endswith(ext):
            return lang
    return None


def outline(path: str, text: str, limit: int = 120) -> str:
    """`  12  export function routeV2` lines for each symbol, indented as in the file, plus the line count."""
    lang = language(path)
    lines = text.splitlines()
    out: list[str] = []
    for n, line in enumerate(lines, 1):
        if not line.strip() or line.lstrip().startswith(("//", "#", "*", "/*")):
            continue
        sig = _match(lang, line)
        if sig and len(out) < limit:
            out.append(f"{n:>5}  {sig}")
    head = f"{path}: {len(lines)} lines, {len(out)} symbols"
    if not out:
        return head + " (no declarations found; use grep or read_file with a range)"
    more = "" if len(out) < limit else f"\n(first {limit} symbols shown)"
    return head + "\n" + "\n".join(out) + more


def _match(lang: str | None, line: str) -> str | None:
    pats = _PATTERNS.get(lang or "", [])
    for p in pats:
        m = p.match(line)
        if not m:
            continue
        sig = line.rstrip().rstrip("{").rstrip()
        name = next((g for g in reversed(m.groups()) if g and re.fullmatch(r"[A-Za-z_$][\w$]*", g)), "")
        if name in _KEYWORDS:
            return None
        return sig[:160]
    if lang is None and re.match(r"^(export |def |class |func |function |type |interface )", line):
        return line.rstrip()[:160]
    return None
