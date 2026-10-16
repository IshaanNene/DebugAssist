"""A node's exception is persisted, traced and served by the API: credentials in it are redacted first (P1-2)."""

from __future__ import annotations

import asyncio
from typing import Any, cast

from debugassist.pipeline.graph import _run_node  # pyright: ignore[reportPrivateUsage]
from debugassist.pipeline.state import RunState


def test_a_failing_node_persists_no_credentials() -> None:
    async def boom(state: RunState, deps: Any) -> dict[str, Any]:
        raise RuntimeError(
            "Command '['git', 'push', 'https://x-access-token:ghs_abcdefghijkl0123@github.com/a/b.git']' failed; "
            "GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz OPEN_ROUTER_API_KEY=sk-or-v1-0123456789abcdef"
        )

    logged: list[str] = []
    update = asyncio.run(
        _run_node(
            "pr_and_notify",
            "deterministic",
            boom,
            RunState(run_id="r", issue_ref="x"),
            cast(Any, None),
            logged.append,
        )
    )
    text = " ".join(update["errors"]) + " ".join(logged)
    assert update["status"] == "failed"
    for secret in ("ghs_abcdefghijkl0123", "ghp_abcdefghij", "sk-or-v1-0123456789abcdef"):
        assert secret not in text
    assert "RuntimeError" in text  # the diagnosis survives
