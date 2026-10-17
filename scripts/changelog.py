"""Release notes from conventional commits (ROADMAP-100 098): `python scripts/changelog.py [<since-ref>]`.

Groups the subjects of the commits since `<since-ref>` (default: the last tag, else the whole history) by type,
newest first, and prints Markdown. Only subjects are used: bodies stay in the history.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys

GROUPS = {"feat": "Features", "fix": "Fixes", "perf": "Performance", "refactor": "Refactoring", "test": "Tests",
          "docs": "Documentation", "ci": "CI", "build": "Build", "chore": "Chores"}  # fmt: skip
SUBJECT = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?(?P<bang>!)?: (?P<text>.+)$")


def git(*args: str) -> str:
    exe = shutil.which("git") or "git"
    return subprocess.run([exe, *args], capture_output=True, text=True, check=False).stdout.strip()  # noqa: S603


def notes(since: str | None) -> str:
    since = since or git("describe", "--tags", "--abbrev=0") or None
    rng = [f"{since}..HEAD"] if since else []
    grouped: dict[str, list[str]] = {}
    for line in git("log", "--no-merges", "--format=%h %s", *rng).splitlines():
        sha, _, subject = line.partition(" ")
        m = SUBJECT.match(subject)
        kind = m.group("type") if m and m.group("type") in GROUPS else "other"
        scope = f"**{m.group('scope')}**: " if m and m.group("scope") else ""
        text = m.group("text") if m else subject
        breaking = " ⚠ breaking" if m and m.group("bang") else ""
        grouped.setdefault(kind, []).append(f"- {scope}{text}{breaking} ({sha})")
    title = f"## Changes since {since}" if since else "## Changes"
    parts = [title]
    for kind in [*GROUPS, "other"]:
        if grouped.get(kind):
            parts += ["", f"### {GROUPS.get(kind, 'Other')}", "", *grouped[kind]]
    return "\n".join(parts) + "\n"


if __name__ == "__main__":
    print(notes(sys.argv[1] if len(sys.argv) > 1 else None), end="")
