"""A no-model localization control: where would the bug be if nobody reasoned at all?

1. The innermost in-app stack frame of the issue's latest event (Vitals: frames are innermost last).
2. Otherwise, the first function the report calls that is defined in the repository (found by a plain text search
   for its definition), skipping names the report defines itself and common language built-ins.
3. Otherwise, nothing.

Scored by the same `score.rca_verdict` as the pipeline, so "exact" means the same file and function. If the
pipeline's localization does not beat this, the investigation is not earning its cost on that set.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

from debugassist.llm.workspace_tools import is_test_path

SOURCE_EXT = {"python": (".py",), "go": (".go",), "typescript": (".ts", ".tsx", ".js", ".mjs")}
SKIP_DIRS = {
    ".git",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "docs",
    "doc",
    "examples",
    "example",
    "benchmarks",
    "bench",
    ".venv",
    "__pycache__",
    ".DebugAssist",
}
# Calls that say nothing about where a bug is: output, conversions, test scaffolding, language built-ins.
NOISE = {
    *[
        "print",
        "len",
        "str",
        "int",
        "float",
        "bool",
        "list",
        "dict",
        "set",
        "tuple",
        "range",
        "repr",
        "type",
        "isinstance",
        "sorted",
        "map",
        "filter",
        "zip",
    ],
    *[
        "enumerate",
        "next",
        "iter",
        "open",
        "super",
        "object",
        "Exception",
        "ValueError",
        "TypeError",
        "require",
        "log",
        "error",
        "warn",
    ],
    *[
        "Println",
        "Printf",
        "Sprintf",
        "Print",
        "Errorf",
        "Fatal",
        "Fatalf",
        "Setenv",
        "Getenv",
        "main",
        "make",
        "append",
        "new",
        "panic",
    ],
    *[
        "console",
        "expect",
        "describe",
        "it",
        "test",
        "assert",
        "Date",
        "String",
        "Number",
        "Array",
        "Object",
        "JSON",
        "Promise",
        "Error",
    ],
    *["timedelta", "datetime", "Decimal"],
}
CALL = re.compile(r"([A-Za-z_]\w*)\s*\(")
DEFINES = re.compile(r"\b(?:def|class|func|function|interface|type)\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)")


def _defs(name: str, language: str) -> list[re.Pattern[str]]:
    n = re.escape(name)
    if language == "python":
        return [re.compile(rf"^\s*(?:async\s+)?def\s+{n}\s*\("), re.compile(rf"^\s*class\s+{n}\b")]
    if language == "go":
        return [re.compile(rf"^func\s+(?:\([^)]*\)\s*)?{n}\s*[\[(]")]
    return [
        re.compile(rf"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*{n}\b"),
        re.compile(rf"^\s*(?:export\s+)?(?:const|let|var)\s+{n}\s*[:=]"),
        re.compile(rf"^\s*(?:export\s+)?(?:abstract\s+)?class\s+{n}\b"),
        re.compile(rf"^\s+(?:(?:public|private|protected|static|async|override)\s+)*{n}\s*\([^)]*\)\s*[:{{]"),
    ]


def frame_location(event: dict[str, Any]) -> dict[str, str] | None:
    """The innermost in-app frame (Vitals keeps frames innermost last)."""
    raw: list[Any] = event.get("frames") or []
    frames: list[dict[str, Any]] = [
        cast(dict[str, Any], f)
        for f in raw
        if isinstance(f, dict) and cast(dict[str, Any], f).get("in_app", True)
    ]
    if not frames:
        return None
    f = frames[-1]
    file, fn = str(f.get("file") or ""), str(f.get("function") or "")
    if not file:
        return None
    if file.startswith("/") and "/src/" in file:  # an absolute path inside a container: keep it repo-relative
        file = "src/" + file.split("/src/", 1)[1]
    return {"file": file, "function": fn, "how": "top in-app frame"}


def called_names(text: str) -> list[str]:
    """Functions the report calls, in order, minus the ones it defines itself and the noise."""
    own = set(DEFINES.findall(text))
    out: list[str] = []
    for name in CALL.findall(text):
        if name not in own and name not in NOISE and name not in out and not name.isupper():
            out.append(name)
    return out


def _sources(repo: Path, language: str) -> list[Path]:
    exts = SOURCE_EXT.get(language, ())
    files: list[Path] = []
    for p in sorted(repo.rglob("*")):
        rel = p.relative_to(repo)
        if p.suffix in exts and p.is_file() and not SKIP_DIRS & set(rel.parts) and not is_test_path(str(rel)):
            files.append(p)
    return files


def definition(name: str, repo: Path, language: str) -> str | None:
    """The repo-relative file that defines `name`, or None (first match in path order)."""
    pats = _defs(name, language)
    for p in _sources(repo, language):
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        if any(pat.search(line) for line in text.splitlines() for pat in pats):
            return str(p.relative_to(repo))
    return None


def report_location(text: str, repo: Path | None, language: str) -> dict[str, str] | None:
    if repo is None or not repo.is_dir():
        return None
    for name in called_names(text):
        if file := definition(name, repo, language):
            return {"file": file, "function": name, "how": f"first called function the repo defines ({name})"}
    return None


def report_text(issue: dict[str, Any]) -> str:
    report: dict[str, Any] = issue.get("report") or {}
    parts = [str(issue.get("title") or ""), *(str(report.get(k) or "") for k in ("body", "description"))]
    return "\n".join(p for p in parts if p)


def locate(issue: dict[str, Any], repo: Path | None) -> dict[str, str] | None:
    """The control's location for an issue (a RunState issue as a dict), searching `repo` for definitions."""
    return frame_location(issue.get("latest_event") or {}) or report_location(
        report_text(issue), repo, str(issue.get("language") or "")
    )
