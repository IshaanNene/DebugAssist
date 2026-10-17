"""Pre-commit and CI: fail when a staged file holds a credential-shaped string (ROADMAP-100 009, 097).

Uses the same patterns that redact errors and traces (`core.redaction`), so a key format the pipeline masks is
also a key format that cannot be committed. Test fixtures and the red-team catalogue hold fake keys on purpose and
are skipped.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from debugassist.core.redaction import DISCORD_WEBHOOK, KEY_PREFIXED, URL_USERINFO

SKIP = re.compile(
    r"(^|/)(tests?|fixtures)/|^evals/redteam/|^groundtruth/|\.lock$|^uv\.lock$|pnpm-lock\.yaml$"
)
PATTERNS = {
    "API key or token": KEY_PREFIXED,
    "credentials in a URL": URL_USERINFO,
    "Discord webhook": DISCORD_WEBHOOK,
}
# Not secrets: templates, elided examples, and the dev stack's published local defaults (`debugassist`, `-local`).
PLACEHOLDER = re.compile(
    r"\{|\$\{|<[a-z_-]+>|\*\*\*|\[token\]|…|example|debugassist(-dev)?@|debugassist-local", re.I
)


def findings(path: Path) -> list[str]:
    try:
        text = path.read_text(errors="strict")
    except (OSError, UnicodeDecodeError):
        return []  # binary or unreadable: not this check's business
    out: list[str] = []
    for n, line in enumerate(text.splitlines(), 1):
        for what, rx in PATTERNS.items():
            m = rx.search(line)
            if m and not PLACEHOLDER.search(m.group(0)):
                out.append(f"{path}:{n}: {what} ({m.group(0)[:8]}…)")
    return out


def main(argv: list[str]) -> int:
    hits = [h for a in argv if not SKIP.search(a) for h in findings(Path(a))]
    for h in hits:
        print(h, file=sys.stderr)
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
