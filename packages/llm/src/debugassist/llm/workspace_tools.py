"""Coding tools for agents, confined to the run's sandbox worktree (PLAN amendment A3).

Files: path-confined (no escapes, no secrets, no .git). Commands: guarded and executed in a
network-less container (see integrations.sandbox).
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Callable
from pathlib import Path

from langchain_core.tools import BaseTool, tool

from debugassist.core import ablation
from debugassist.core.guards import GuardError, confine
from debugassist.core.outline import outline
from debugassist.integrations.sandbox import Sandbox

SKIP = {".git", "node_modules", "dist", ".corepack", ".venv", "__pycache__", "vendor"}
# DA_CONTEXT=lean (ROADMAP P15): a read returns at most this many lines (agents name wide ranges, so a default
# window alone changed nothing in the first lean run); command output keeps its
# failure lines and tail in the history, and the full log stays behind a handle for read_log.
LEAN_READ = 120
LEAN_TAIL = 40
LEAN_ERRORS = 25
_FAILURE = re.compile(
    r"\b(FAIL|FAILED|ERROR|Error|error|panic|Traceback|Exception|AssertionError|expected|✗|×)\b|^\s*[✗×]|^E\s"
)


def window_footer(path: str, first: int, last: int, total: int) -> str:
    if last >= total and first <= 1:
        return ""
    return (
        f"\n… showing lines {first}–{last} of {total}. outline_file('{path}') lists its symbols with line "
        "numbers; read another range with start_line/end_line."
    )


def summarize_log(output: str, handle: str) -> str:
    """Failure lines (deduplicated, in order) and the tail of a command's output, with a handle to the rest."""
    lines = output.splitlines()
    if len(lines) <= LEAN_TAIL + LEAN_ERRORS:
        return output
    tail_from = len(lines) - LEAN_TAIL
    seen: set[str] = set()
    errors: list[str] = []
    for n, line in enumerate(lines[:tail_from], 1):
        key = line.strip()
        if key and key not in seen and _FAILURE.search(line):
            seen.add(key)
            errors.append(f"{n:>5}  {line[:240]}")
            if len(errors) >= LEAN_ERRORS:
                break
    parts = [f"[{len(lines)} lines of output; full log: read_log('{handle}', start_line, end_line)]"]
    if errors:
        parts += ["failure lines before the tail:", *errors]
    parts += [
        f"last {LEAN_TAIL} lines:",
        *(f"{n:>5}  {lines[n - 1]}" for n in range(tail_from + 1, len(lines) + 1)),
    ]
    return "\n".join(parts)


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def replace_ignoring_indent(text: str, old: str, new: str) -> str | None:
    """`old` → `new` where `old` matches exactly one block of `text` once leading whitespace is ignored;
    `new` is re-indented by the same offset. None when there is no unique match. Agents often guess the
    indentation wrong; this keeps an exact-text edit tool from burning turns on it."""
    lines = text.splitlines(keepends=True)
    want = [ln.strip() for ln in old.strip("\n").splitlines()]
    if not want or not any(want):
        return None
    hits = [
        i
        for i in range(len(lines) - len(want) + 1)
        if all(lines[i + j].strip() == w for j, w in enumerate(want))
    ]
    if len(hits) != 1:
        return None
    i = hits[0]
    first = next(j for j, w in enumerate(want) if w)
    file_ind = _indent(lines[i + first])
    old_ind = _indent(old.strip("\n").splitlines()[first])
    out: list[str] = []
    for ln in new.strip("\n").splitlines():
        if not ln.strip():
            out.append("")
        elif ln.startswith(old_ind):
            out.append(file_ind + ln[len(old_ind) :])
        else:
            out.append(file_ind + ln.lstrip())
    end = "\n" if lines[i + len(want) - 1].endswith("\n") else ""
    return "".join(lines[:i]) + "\n".join(out) + end + "".join(lines[i + len(want) :])


def closest_lines(text: str, old: str, context: int = 3) -> str:
    """Where `old` most likely was meant to match, with line numbers (for a failed edit)."""
    import difflib

    first = next((ln.strip() for ln in old.splitlines() if ln.strip()), "")
    lines = text.splitlines()
    if not first or not lines:
        return ""
    scored = sorted(
        ((difflib.SequenceMatcher(None, first, ln.strip()).ratio(), n) for n, ln in enumerate(lines)),
        reverse=True,
    )
    ratio, best = scored[0]
    if ratio < 0.6:
        return ""
    lo, hi = max(0, best - context), min(len(lines), best + context + len(old.splitlines()))
    return "\n".join(f"{n + 1:>5}  {lines[n]}" for n in range(lo, hi))


def build_workspace_tools(
    sb: Sandbox,
    *,
    allow_edits: bool,
    allow_commands: bool,
    editable: Callable[[str], bool] | None = None,
    workdir: str = ".",
) -> list[BaseTool]:
    """`editable(path)` restricts which files may be written (e.g. tests only while reproducing)."""
    root = sb.worktree
    lean = ablation.lean()
    logs: dict[str, str] = {}

    def can_edit(path: str) -> str | None:
        if editable is not None and not editable(path):
            return f"blocked: {path} cannot be modified in this step"
        return None

    def resolve(path: str, *, new: bool = False) -> str:
        """Repository-relative first; otherwise relative to the component directory commands run in."""
        clean = path.strip()
        while clean.startswith(
            "./"
        ):  # only a literal "./" — never strip "../" or "/" (confine must see them)
            clean = clean[2:]
        clean = clean or "."
        if (
            workdir in (".", "")
            or clean in (".",)
            or clean.startswith(("/", "..", workdir.rstrip("/") + "/"))
        ):
            return clean
        here, there = root / clean, root / workdir / clean
        if new:
            top = clean.split("/", 1)[0]
            use_comp = not (root / top).exists() and (root / workdir / top).exists()
            return f"{workdir.rstrip('/')}/{clean}" if use_comp else clean
        return f"{workdir.rstrip('/')}/{clean}" if not here.exists() and there.exists() else clean

    @tool
    def list_dir(path: str = ".") -> str:
        """List files and folders under a directory of the repository."""
        try:
            p = confine(root, path)
        except GuardError as exc:
            return str(exc)
        if not p.is_dir():
            return f"{path} is not a directory"
        rows = sorted(f"{c.name}/" if c.is_dir() else c.name for c in p.iterdir() if c.name not in SKIP)
        return "\n".join(rows[:300])

    @tool
    def read_file(path: str, start_line: int = 1, end_line: int = 0) -> str:
        """Read a repository file with line numbers (optionally a line range)."""
        path = resolve(path)
        try:
            p = confine(root, path)
        except GuardError as exc:
            return str(exc)
        if not p.is_file():
            return f"{path} not found"
        lines = p.read_text(errors="replace").splitlines()
        first = max(1, start_line)
        span = LEAN_READ if lean else 400  # lean: agents ask for 180–260-line ranges; cap those too
        end = min(end_line or len(lines), len(lines), first + span - 1)
        body = "\n".join(f"{n:>5}  {lines[n - 1]}" for n in range(first, end + 1)) or "(empty file)"
        return body + (window_footer(path, first, end, len(lines)) if lean else "")

    @tool
    def outline_file(path: str) -> str:
        """List a file's functions, classes and types with their line numbers — read only the range you need."""
        path = resolve(path)
        try:
            p = confine(root, path)
        except GuardError as exc:
            return str(exc)
        if not p.is_file():
            return f"{path} not found"
        return outline(path, p.read_text(errors="replace"))

    @tool
    def grep(pattern: str, path_glob: str = "**/*", max_results: int = 40) -> str:
        """Regex search across repository files (path_glob like 'src/**/*.ts')."""
        try:
            rx = re.compile(pattern)
        except re.error as exc:
            return f"bad regex: {exc}"
        hits: list[str] = []
        for f in sorted(root.rglob("*")):
            rel = f.relative_to(root)
            if (
                any(part in SKIP for part in rel.parts)
                or not f.is_file()
                or not fnmatch.fnmatch(str(rel), path_glob)
            ):
                continue
            try:
                for i, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
                    if rx.search(line):
                        hits.append(f"{rel}:{i}: {line.strip()[:200]}")
                        if len(hits) >= max_results:
                            return "\n".join(hits)
            except OSError:
                continue
        return "\n".join(hits) or "no matches"

    @tool
    def edit_file(path: str, old_text: str, new_text: str) -> str:
        """Replace one occurrence of old_text with new_text in a file. old_text must match exactly once
        (leading indentation may differ: a unique block matching apart from indentation is re-indented)."""
        path = resolve(path)
        if (why := can_edit(path)) is not None:
            return why
        try:
            p = confine(root, path)
        except GuardError as exc:
            return str(exc)
        if not p.is_file():
            return f"{path} not found"
        text = p.read_text()
        n = text.count(old_text)
        if n == 1:
            p.write_text(text.replace(old_text, new_text))
            return f"edited {path}"
        if n == 0 and (fixed := replace_ignoring_indent(text, old_text, new_text)) is not None:
            p.write_text(fixed)
            return (
                f"edited {path} (old_text matched apart from indentation; new_text re-indented to the file)"
            )
        hint = closest_lines(text, old_text) if n == 0 else ""
        msg = f"old_text matched {n} times; it must match exactly once (include more surrounding lines)"
        return msg + (f". Closest lines in {path} (copy them exactly):\n{hint}" if hint else "")

    @tool
    def write_file(path: str, content: str) -> str:
        """Create or overwrite a file (use for new test files)."""
        path = resolve(path, new=True)
        if (why := can_edit(path)) is not None:
            return why
        try:
            p = confine(root, path)
        except GuardError as exc:
            return str(exc)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"wrote {path} ({len(content.splitlines())} lines)"

    @tool
    def run_command(command: str) -> str:
        """Run a shell command (tests, type checks) in a network-less container, from the component directory."""
        try:
            res = sb.run(command, workdir=workdir)
        except GuardError as exc:
            return str(exc)
        if not lean:
            return f"exit code {res.exit_code}\n{res.output[-6000:]}"
        handle = f"cmd-{len(logs) + 1}"
        logs[handle] = res.output
        return f"exit code {res.exit_code}\n{summarize_log(res.output, handle)}"

    @tool
    def read_log(handle: str, start_line: int = 1, end_line: int = 0) -> str:
        """Read lines of an earlier run_command's full output by its handle (e.g. 'cmd-2')."""
        if handle not in logs:
            return f"no log {handle!r}; known: {', '.join(logs) or 'none yet'}"
        lines = logs[handle].splitlines()
        first = max(1, start_line)
        end = min(end_line or len(lines), len(lines), first + 199)
        return "\n".join(f"{n:>5}  {lines[n - 1]}" for n in range(first, end + 1)) or "(empty)"

    tools: list[BaseTool] = [list_dir, read_file, grep]
    if lean:
        tools.append(outline_file)
    if allow_edits:
        tools += [edit_file, write_file]
    if allow_commands:
        tools.append(run_command)
        if lean:
            tools.append(read_log)
    return tools


def changed_files(diff: str) -> list[str]:
    return sorted({m.group(1) for m in re.finditer(r"^\+\+\+ b/(.+)$", diff, re.M)})


def is_test_path(path: str) -> bool:
    return bool(
        re.search(
            r"(^|/)(test|tests|__tests__|e2e)/|\.(test|spec)\.|_test\.(go|py)$|(^|/)test_[^/]+\.py$", path
        )
    ) or Path(path).name.startswith("test_")
