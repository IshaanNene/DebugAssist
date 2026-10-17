"""Make every workspace package importable in tests even if editable .pth files are skipped.

On macOS, files under ~/Desktop can pick up the UF_HIDDEN flag, and Python 3.13+ ignores hidden
.pth files, which silently drops editable installs. `make sync` clears the flag; this is the
test-time safety net.
"""

import sys
from pathlib import Path

for src in sorted(
    [*Path(__file__).parent.glob("packages/*/src"), *Path(__file__).parent.glob("sources/*/service/src")]
):
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


@pytest.fixture(autouse=True)
def _no_ambient_credentials(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests never see the developer's credentials: not exported ones (`gh`, Codespaces and CI runners set
    GITHUB_TOKEN), and not the repository's `.env`. Either would switch an integration to live (audit P2-10)."""
    if os.environ.get("DA_LIVE_TESTS") == "1" and "live" in request.keywords:
        return
    from debugassist.core.settings import Integration, Settings, get_settings

    for name, field in Settings.model_fields.items():
        aliases = getattr(field.validation_alias, "choices", None) or []
        for env in {name, *(str(a) for a in aliases)}:
            monkeypatch.delenv(env.upper(), raising=False)
    for i in Integration:
        monkeypatch.delenv(f"DA_MODE_{i.name}", raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    # Gates made without an explicit audit path write to a per-test file, never the developer's .data/audit.jsonl.
    from debugassist.core import policy

    monkeypatch.setattr(policy, "DEFAULT_AUDIT", request.getfixturevalue("tmp_path") / "audit.jsonl")
    from debugassist.core import logs

    monkeypatch.setattr(logs, "LOGS", request.getfixturevalue("tmp_path") / "logs")
    get_settings.cache_clear()
    request.addfinalizer(get_settings.cache_clear)
