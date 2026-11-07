"""The root conftest's no-network guard: non-live tests cannot reach other hosts, and loopback still works."""

from __future__ import annotations

import socket
import threading

import httpx
import pytest


@pytest.mark.network_guard_selftest
def test_outbound_connections_and_lookups_are_refused() -> None:
    with pytest.raises(ConnectionRefusedError, match="non-live test"):
        socket.getaddrinfo("openrouter.ai", 443)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with s, pytest.raises(ConnectionRefusedError, match="non-live test"):
        s.connect(("1.1.1.1", 443))
    with pytest.raises(httpx.ConnectError):  # httpx sees an ordinary refused connection
        httpx.get("https://openrouter.ai/api/v1/models", timeout=2)


def test_loopback_still_works() -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    t = threading.Thread(target=lambda: srv.accept()[0].close())
    t.start()
    with socket.create_connection(("localhost", port), timeout=2):
        pass
    t.join(2)
    srv.close()
