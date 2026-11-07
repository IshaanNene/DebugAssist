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

import ipaddress  # noqa: E402
import os  # noqa: E402
import socket  # noqa: E402
from collections.abc import Callable  # noqa: E402
from typing import Any  # noqa: E402

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
    # The GitHub App poller's state likewise (a test that forgets one path must not touch the real one).
    from debugassist.pipeline import app_cli

    app_dir = request.getfixturevalue("tmp_path") / "app"
    for name in ("QUEUE", "SEEN", "LOCK", "METRICS", "OUTCOMES", "REVIEWS", "CI_QUEUE"):
        monkeypatch.setattr(app_cli, name, app_dir / getattr(app_cli, name).name)
    get_settings.cache_clear()
    request.addfinalizer(get_settings.cache_clear)


class NetworkBlocked(ConnectionRefusedError):
    """A test that is not marked `live` tried to reach a host other than this machine."""


def _local(host: object) -> bool:
    if host is None or host in ("", "localhost") or (isinstance(host, str) and host.endswith(".localhost")):
        return True
    try:
        return ipaddress.ip_address(str(host).split("%")[0]).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def _no_outbound_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test not marked `live` runs without the network: a connection or DNS lookup for anything but loopback
    or a unix socket raises `NetworkBlocked` and fails the test, even if the code under test swallows the error
    (a hidden call to openrouter.ai once made a "replayed" contract test depend on the live API). Child processes
    (git, node, docker) are not covered; they run against local fixtures or Docker's unix socket."""
    if os.environ.get("DA_LIVE_TESTS") == "1" and "live" in request.keywords:
        return
    attempts: list[str] = []

    def refuse(what: str) -> NetworkBlocked:
        attempts.append(what)
        return NetworkBlocked(f"network access in a non-live test: {what}")

    real_connect: Callable[..., Any] = socket.socket.connect
    real_connect_ex: Callable[..., Any] = socket.socket.connect_ex
    real_getaddrinfo: Callable[..., Any] = socket.getaddrinfo

    def allowed(sock: socket.socket, address: Any) -> bool:
        return sock.family == getattr(socket, "AF_UNIX", None) or (
            isinstance(address, tuple) and _local(address[0])  # pyright: ignore[reportUnknownArgumentType]
        )

    def connect(self: socket.socket, address: Any) -> None:
        if not allowed(self, address):
            raise refuse(f"connect {address!r}")
        real_connect(self, address)

    def connect_ex(self: socket.socket, address: Any) -> int:
        if not allowed(self, address):
            raise refuse(f"connect {address!r}")
        return real_connect_ex(self, address)

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if not _local(host.decode() if isinstance(host, bytes) else host):
            raise refuse(f"resolve {host!r}")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    # OpenRouter's model catalog: an empty, fresh per-test cache (unknown models get the conservative defaults).
    from debugassist.core import openrouter

    empty = request.getfixturevalue("tmp_path") / "openrouter_models.json"
    empty.write_text("[]")
    monkeypatch.setattr(openrouter, "CACHE", empty)
    openrouter.model_info.cache_clear()
    request.addfinalizer(openrouter.model_info.cache_clear)

    def check() -> None:
        if attempts and "network_guard_selftest" not in request.keywords:
            pytest.fail(f"non-live test used the network: {'; '.join(attempts[:3])}", pytrace=False)

    request.addfinalizer(check)
