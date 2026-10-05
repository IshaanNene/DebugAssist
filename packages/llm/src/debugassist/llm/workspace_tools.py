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

from debugassist.core.guards import GuardError, confine
from debugassist.integrations.sandbox import Sandbox

SKIP = {".git", "node_modules", "dist", ".corepack", ".venv", "__pycache__", "vendor"}


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

    def can_edit(path: str) -> str | None:
        if editable is not None and not editable(path):
            return f"blocked: {path} cannot be modified in this step"
        return None

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
        try:
            p = confine(root, path)
        except GuardError as exc:
            return str(exc)
        if not p.is_file():
            return f"{path} not found"
        lines = p.read_text(errors="replace").splitlines()
        end = min(end_line or len(lines), len(lines), start_line + 399)
        return (
            "\n".join(f"{n:>5}  {lines[n - 1]}" for n in range(max(1, start_line), end + 1)) or "(empty file)"
        )

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
        """Replace one exact occurrence of old_text with new_text in a file. old_text must match exactly once."""
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
        if n != 1:
            return f"old_text matched {n} times; it must match exactly once (include more surrounding lines)"
        p.write_text(text.replace(old_text, new_text))
        return f"edited {path}"

    @tool
    def write_file(path: str, content: str) -> str:
        """Create or overwrite a file (use for new test files)."""
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
        return f"exit code {res.exit_code}\n{res.output[-6000:]}"

    tools: list[BaseTool] = [list_dir, read_file, grep]
    if allow_edits:
        tools += [edit_file, write_file]
    if allow_commands:
        tools.append(run_command)
    return tools


def changed_files(diff: str) -> list[str]:
    return sorted({m.group(1) for m in re.finditer(r"^\+\+\+ b/(.+)$", diff, re.M)})


def is_test_path(path: str) -> bool:
    return bool(
        re.search(
            r"(^|/)(test|tests|__tests__|e2e)/|\.(test|spec)\.|_test\.(go|py)$|(^|/)test_[^/]+\.py$", path
        )
    ) or Path(path).name.startswith("test_")
