"""Install a sitecustomize.py into the venv that puts every workspace package on sys.path.

Why: on this macOS setup every file created inside a dot-directory under ~/Desktop gets the
UF_HIDDEN flag within seconds, and Python 3.13+ skips hidden .pth files — which silently breaks
uv's editable installs. sitecustomize is imported normally (the hidden flag doesn't matter), so it
survives `uv run` re-syncs. Harmless elsewhere. Run by `make sync`.
"""

import sysconfig
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = f"""# Written by scripts/venv_path_hook.py — see that file for why.
import sys
from pathlib import Path

for _src in sorted([*Path({str(ROOT)!r}).glob("packages/*/src"), *Path({str(ROOT)!r}).glob("sources/*/service/src")]):
    if str(_src) not in sys.path:
        sys.path.append(str(_src))
"""

target = Path(sysconfig.get_paths()["purelib"]) / "sitecustomize.py"
target.write_text(HOOK)
print(f"wrote {target}")
