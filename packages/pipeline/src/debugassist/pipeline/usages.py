"""How the code at fault is used elsewhere in its repository — for DA_SECOND_REPRO=callers.

A report shows one example; the cases a fix must also keep working are in the code's other uses: its documentation,
type stubs, existing tests and callers. This collects them mechanically (git grep, no model), so the independent
check sees a source the report does not have.

Names searched: the root-cause function and its class, and the identifiers in the report's code that the repository
defines. Each hit comes with a few lines of context; documentation and stubs first, then tests, then other source,
a few per name, within a character budget.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping
from pathlib import Path

CONTEXT = 8  # lines either side of a hit
PER_NAME = 6  # snippets per name
BUDGET = 8000  # characters in all
SKIP = re.compile(r"(^|/)(CHANGELOG|CHANGES|HISTORY|NEWS)[^/]*$|(^|/)\.github/|(^|/)\.DebugAssist/", re.I)
_IDENT = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_CODE = re.compile(r"```[^\n]*\n(.*?)```", re.S)


def _rank(path: str) -> int:
    if path.endswith((".rst", ".md", ".txt")) or path.startswith(("docs/", "doc/")):
        return 0
    if path.endswith((".pyi", ".d.ts")):
        return 1
    if re.search(r"(^|/)(tests?|__tests__)/|(^|/)test_[^/]+$|[._-](test|spec)\.", path):
        return 2
    return 3


def _git(worktree: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=worktree, capture_output=True, text=True, check=False)
    return out.stdout


def defined(worktree: Path, name: str) -> bool:
    """Whether the repository defines `name` (a def, class, function, type or exported const)."""
    pat = rf"(def|class|function|type|interface|const|let|var|func)[[:space:]]+{re.escape(name)}([^A-Za-z0-9_]|$)"
    return subprocess.run(["git", "grep", "-q", "-E", pat], cwd=worktree, check=False).returncode == 0


def report_text(report: Mapping[str, object]) -> str:
    """The report's own text (its string fields, newlines intact), not its JSON: code blocks must still match."""
    return "\n".join(v for v in report.values() if isinstance(v, str))


def names_for(worktree: Path, function: str | None, report: str) -> list[str]:
    """The root-cause function (last part, and its class) and the report's code identifiers the repo defines."""
    out: list[str] = []
    for part in (function or "").replace("::", ".").split("."):
        if part and part not in out:
            out.append(part)
    code = "\n".join(_CODE.findall(report))  # identifiers from prose would be guesses
    found = [
        i
        for i in dict.fromkeys(_IDENT.findall(code))
        if len(i) > 2 and i not in out and not i.startswith("__") and defined(worktree, i)
    ]
    # the most specific first: a name used in few places says more about this code than a common one
    found.sort(key=lambda i: len(_git(worktree, "grep", "-n", "-w", "-I", "--", i).splitlines()))
    return (out + found)[:6]


def collect(worktree: Path, names: list[str], *, exclude: set[str] | None = None) -> str:
    """Snippets of each name's uses, best sources first; '' when there are none."""
    exclude = exclude or set()
    parts: list[str] = []
    used = 0
    for name in names:
        hits: dict[str, list[int]] = {}
        for line in _git(worktree, "grep", "-n", "-w", "-I", "--", name).splitlines():
            path, _, rest = line.partition(":")
            num = rest.split(":", 1)[0]
            if path in exclude or SKIP.search(path) or not num.isdigit():
                continue
            hits.setdefault(path, []).append(int(num))
        taken = 0
        for path in sorted(hits, key=lambda p: (_rank(p), p)):
            if taken >= PER_NAME:
                break
            lines = (worktree / path).read_text(errors="replace").splitlines()
            last_end = -1
            for n in hits[path]:
                if taken >= PER_NAME or n - 1 <= last_end:
                    continue
                lo, hi = max(0, n - 1 - CONTEXT), min(len(lines), n + CONTEXT)
                body = "\n".join(lines[lo:hi])
                snippet = f"--- {path}:{lo + 1}-{hi} (uses `{name}`)\n{body}\n"
                if used + len(snippet) > BUDGET:
                    return "\n".join(parts)
                parts.append(snippet)
                used += len(snippet)
                taken += 1
                last_end = hi - 1
    return "\n".join(parts)
