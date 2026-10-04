from __future__ import annotations

from typing import Protocol

from debugassist.core.settings import Mode
from debugassist.decisions.schema import ClefRequest, ClefResponse

# USD per million input tokens on Workers AI (2026-10-04). Clef produces no output tokens.
WORKERS_AI_PRICE_PER_MTOK = {"clef": 0.24, "clef-flash": 0.09}


class DecisionBackend(Protocol):
    """Answers a Clef-format request. Implementations never act on the answer."""

    name: str
    mode: Mode

    async def run(self, request: ClefRequest) -> ClefResponse: ...

    def cost_usd(self, response: ClefResponse) -> float: ...

    async def aclose(self) -> None: ...
