"""Make every workspace package importable in tests even if editable .pth files are skipped.

On macOS, files under ~/Desktop can pick up the UF_HIDDEN flag, and Python 3.13+ ignores hidden
.pth files, which silently drops editable installs. `make sync` clears the flag; this is the
test-time safety net.
"""

import sys
from pathlib import Path

for src in sorted(Path(__file__).parent.glob("packages/*/src")):
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

import os  # noqa: E402

import pytest  # noqa: E402


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("DA_LIVE_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="live test: set DA_LIVE_TESTS=1 (uses real API keys, costs money)")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)
