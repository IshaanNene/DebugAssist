"""N2 context_collector: the evidence bundle."""

from __future__ import annotations

from typing import Any

from debugassist.pipeline import (
    collector,
)
from debugassist.pipeline.deps import Deps
from debugassist.pipeline.nodes.common import bot_branch, sandbox_for
from debugassist.pipeline.state import (
    RunState,
)


async def context_collector(state: RunState, deps: Deps) -> dict[str, Any]:
    issue = state.issue
    assert issue
    # The sandbox worktree at the shipped release: code search and the fix both work on it.
    sb = sandbox_for(state)
    sb.create(f"v{issue.last_version}", bot_branch(issue, deps))
    return await collector.collect(state, deps)
