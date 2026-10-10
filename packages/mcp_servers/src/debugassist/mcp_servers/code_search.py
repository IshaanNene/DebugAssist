"""code-search MCP server (Sourcegraph's role): search, read, symbols, blame, owners."""

from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from debugassist.core import ablation
from debugassist.core.guards import GuardError, confine
from debugassist.core.outline import outline
from debugassist.mcp_servers.common import cap, with_evidence
from debugassist.mcp_servers.repos import repo_roots, resolve

mcp = FastMCP("code-search", log_level="WARNING")
LEAN_READ = 120
SKIP_DIRS = {".git", "node_modules", "dist", ".venv", "__pycache__", ".corepack", "test-results", "vendor"}
TEXT_EXT = {
    ".ts",
    ".tsx",
    ".js",
    ".mjs",
    ".py",
    ".go",
    ".json",
    ".yaml",
    ".yml",
    ".md",
    ".toml",
    ".sql",
    ".css",
    ".html",
    ".sh",
}
SYMBOL_DEF = [
    r"(?:export\s+)?(?:async\s+)?function\s+{name}\b",
    r"(?:export\s+)?(?:const|let|var)\s+{name}\s*=",
    r"(?:export\s+)?(?:class|interface|type|enum)\s+{name}\b",
    r"^\s*(?:async\s+)?def\s+{name}\s*\(",
    r"^\s*class\s+{name}\b",
    r"^func\s+(?:\([^)]*\)\s*)?{name}\s*\(",
    r"^\s*(?:private\s+|public\s+|protected\s+|static\s+|async\s+)*{name}\s*(?:=\s*(?:async\s*)?\(|\()",
]


def _files(root: Path, path_glob: str | None) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts) or not p.is_file() or p.suffix not in TEXT_EXT:
            continue
        if path_glob and not fnmatch.fnmatch(str(rel), path_glob):
            continue
        out.append(p)
    return sorted(out)


@mcp.tool()
def list_repos() -> dict[str, Any]:
    """Repositories available to search."""
    return {"repos": sorted(repo_roots())}


@mcp.tool()
def search_code(
    query: str,
    repo: str | None = None,
    regex: bool = False,
    path_glob: str | None = None,
    case_sensitive: bool = False,
    limit: int = 30,
    offset: int = 0,
) -> dict[str, Any]:
    """Search code (literal or regex). Filter by repo and path glob (e.g. 'src/**/*.ts'). Returns file:line matches."""
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(query if regex else re.escape(query), flags)
    hits: list[dict[str, Any]] = []
    for name, root in sorted(repo_roots().items()):
        if repo and name != repo:
            continue
        for f in _files(root, path_glob):
            try:
                lines = f.read_text(errors="replace").splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines, 1):
                if pattern.search(line):
                    hits.append(
                        {
                            "repo": name,
                            "path": str(f.relative_to(root)),
                            "line": i,
                            "text": line.strip()[:240],
                        }
                    )
    return with_evidence("code", "search", {"query": query, **cap(hits, limit, offset)})


@mcp.tool()
def read_file(repo: str, path: str, start_line: int = 1, end_line: int | None = None) -> dict[str, Any]:
    """Read a file (or a line range) with line numbers."""
    try:
        p = confine(resolve(repo), path)
    except GuardError as exc:
        return {"error": str(exc)}
    if not p.is_file():
        return {"error": f"{path} not found in {repo}"}
    lines = p.read_text(errors="replace").splitlines()
    # DA_CONTEXT=lean: a read without a range is a 120-line window; outline_file finds the right one.
    span = LEAN_READ if ablation.lean() and not end_line else 400
    end = min(end_line or len(lines), len(lines), max(1, start_line) + span - 1)
    body = "\n".join(f"{n:>5}  {lines[n - 1]}" for n in range(max(1, start_line), end + 1))
    out: dict[str, Any] = {
        "repo": repo,
        "path": path,
        "start_line": start_line,
        "end_line": end,
        "total_lines": len(lines),
        "content": body,
    }
    if ablation.lean() and end < len(lines):
        out["more"] = (
            "outline_file lists this file's symbols with line numbers; read another range with start_line/end_line"
        )
    return with_evidence("code", "file_excerpt", out)


def outline_file(repo: str, path: str) -> dict[str, Any]:
    """List a file's functions, classes and types with line numbers, so you read only the range you need."""
    try:
        p = confine(resolve(repo), path)
    except GuardError as exc:
        return {"error": str(exc)}
    if not p.is_file():
        return {"error": f"{path} not found in {repo}"}
    return with_evidence(
        "code",
        "outline",
        {"repo": repo, "path": path, "outline": outline(path, p.read_text(errors="replace"))},
    )


if (
    ablation.lean()
):  # only offered in the lean context arm, so the baseline's tool list (and cache prefix) is unchanged
    mcp.tool()(outline_file)


@mcp.tool()
def find_symbol(name: str, repo: str | None = None) -> dict[str, Any]:
    """Find where a function/class/const/method is defined (TypeScript, Python, Go)."""
    if not re.fullmatch(r"[A-Za-z_$][\w$]*", name):
        return {"error": "symbol must be an identifier"}
    patterns = [re.compile(p.format(name=re.escape(name)), re.M) for p in SYMBOL_DEF]
    defs: list[dict[str, Any]] = []
    for rname, root in sorted(repo_roots().items()):
        if repo and rname != repo:
            continue
        for f in _files(root, None):
            text = f.read_text(errors="replace")
            for i, line in enumerate(text.splitlines(), 1):
                if any(p.search(line) for p in patterns):
                    defs.append(
                        {
                            "repo": rname,
                            "path": str(f.relative_to(root)),
                            "line": i,
                            "text": line.strip()[:200],
                        }
                    )
    return with_evidence("code", "symbol", {"symbol": name, "definitions": defs[:20]})


@mcp.tool()
def find_references(name: str, repo: str | None = None, limit: int = 40) -> dict[str, Any]:
    """Find identifier references (whole-word)."""
    return search_code(rf"\b{re.escape(name)}\b", repo=repo, regex=True, case_sensitive=True, limit=limit)


@mcp.tool()
def blame(repo: str, path: str, start_line: int, end_line: int) -> dict[str, Any]:
    """git blame for a line range: who last changed each line, in which commit."""
    root = resolve(repo)
    try:
        confine(root, path)
    except GuardError as exc:
        return {"error": str(exc)}
    out = subprocess.run(
        ["git", "blame", "--line-porcelain", "-L", f"{start_line},{end_line}", "--", path],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if out.returncode:
        return {"error": out.stderr.strip()[:300]}
    rows: list[dict[str, Any]] = []
    cur: dict[str, Any] = {}
    for line in out.stdout.splitlines():
        if re.match(r"^[0-9a-f]{40} ", line):
            sha, _, final, *_ = line.split()
            cur = {"commit": sha[:10], "line": int(final)}
        elif line.startswith("author "):
            cur["author"] = line[7:]
        elif line.startswith("summary "):
            cur["summary"] = line[8:]
        elif line.startswith("\t"):
            cur["text"] = line[1:][:200]
            rows.append(cur)
    return with_evidence("git", "blame", {"repo": repo, "path": path, "lines": rows})


@mcp.tool()
def codeowners_for(repo: str, path: str) -> dict[str, Any]:
    """Owning team for a path (CODEOWNERS; the last matching rule wins)."""
    root = resolve(repo)
    f = root / ".github" / "CODEOWNERS"
    owner: dict[str, Any] = {"repo": repo, "path": path, "team": None, "owners": []}
    if f.is_file():
        for line in f.read_text().splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            rule, *rest = line.split("#", 1)
            parts = rule.split()
            pat = parts[0].lstrip("/")
            hit = pat == "*" or path.startswith(pat.rstrip("*")) or fnmatch.fnmatch(path, pat)
            if hit:
                team = re.search(r"team:([\w-]+)", rest[0]) if rest else None
                owner.update(owners=parts[1:], team=team.group(1) if team else None, rule=pat)
    return with_evidence("code", "owners", owner)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
