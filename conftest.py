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
