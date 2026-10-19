"""The API's OpenAPI schema, written for the dashboard's generated types (ROADMAP-100 064).

    uv run --no-sync python -m debugassist.api.schema        # writes apps/dashboard/openapi.json

`make api-types` runs this and then `openapi-typescript` (apps/dashboard/src/lib/api-schema.ts). The committed schema
is checked against the app by a test (`test_openapi_schema_is_current`), and CI regenerates both files and fails on
any difference, so a response model and the dashboard's types cannot drift apart.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from debugassist.core.policy import ROOT

OUT = ROOT / "apps" / "dashboard" / "openapi.json"


def schema() -> dict[str, Any]:
    from debugassist.api.app import app

    return app.openapi()


def render(spec: dict[str, Any]) -> str:
    """Stable text: sorted keys, two-space indent, a final newline (the drift checks compare bytes)."""
    return json.dumps(spec, indent=2, sort_keys=True) + "\n"


def main(out: Path = OUT) -> None:
    out.write_text(render(schema()))
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
