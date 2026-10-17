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


def test_persisted_run_files_carry_no_credentials(tmp_path: Any) -> None:
    """ROADMAP-100 058: a token anywhere in a node's update (not only in an error) is masked on disk."""
    import json
    from types import SimpleNamespace

    from debugassist.pipeline.graph import _persist  # pyright: ignore[reportPrivateUsage]

    deps = cast(Any, SimpleNamespace(run_dir=tmp_path))
    state = RunState(run_id="r", issue_ref="x")
    update = {
        "notifications": [
            {"kind": "chat", "detail": "posted with GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz0"}
        ]
    }
    _persist(deps, state, "pr_and_notify", update, 12)
    for f in [tmp_path / "state.json", *(tmp_path / "nodes").glob("*.json")]:
        text = f.read_text()
        assert "ghp_abcdefghij" not in text and "[token]" in text
        json.loads(text)
    assert RunState.model_validate_json((tmp_path / "state.json").read_text()).notifications
