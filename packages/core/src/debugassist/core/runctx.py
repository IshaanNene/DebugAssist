"""Per-run values (run id, mode, the repositories code tools may read) for code running inside a run.

They used to be written to `os.environ`, which every run in the process shares: the API process builds deps for
concurrent requests, and one run's `CODE_REPOS` would point another run's code search at the wrong worktree. A
context variable is per asyncio task instead. MCP servers are separate processes and get the same names in their
environment, so `get` falls back to it.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

_values: ContextVar[dict[str, str] | None] = ContextVar("debugassist_run", default=None)


def get(name: str, default: str | None = None) -> str | None:
    """The run's value for `name` (DEBUGASSIST_RUN_ID, DEBUGASSIST_MODE, CODE_REPOS), else the environment's."""
    values = _values.get() or {}
    return values[name] if name in values else os.environ.get(name, default)


@contextmanager
def use(**values: str) -> Generator[None]:
    """Set run values for the code inside the block (and tasks it starts); restored afterwards."""
    token = _values.set({**(_values.get() or {}), **values})
    try:
        yield
    finally:
        _values.reset(token)
