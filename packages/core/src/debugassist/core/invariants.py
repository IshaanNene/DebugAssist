"""Runtime invariants that must hold under `python -O` too (ruff S101 forbids `assert` outside tests)."""

from __future__ import annotations


class InvariantError(RuntimeError):
    """A state the code relies on is missing: a bug in the caller or a corrupt run state, never user input."""
