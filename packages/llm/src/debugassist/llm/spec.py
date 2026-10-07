from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from debugassist.core.settings import get_settings

Effort = Literal["low", "medium", "high"]


class LLMNodeSpec(BaseModel):
    """Per-node configuration (from the agent type; the plan itself is fixed in code)."""

    node: str
    model: str = Field(default_factory=lambda: get_settings().model())
    reasoning_effort: Effort = "medium"
    max_turns: int = 20  # model calls — the main guardrail (talk: past ~20 turns it's a rabbit hole)
    max_tool_calls: int = 40
    max_budget_usd: float = 0.50
    max_wall_s: int = 900  # wall clock for the whole agent step (watchdog)
    mcp_servers: list[str] = Field(default_factory=list[str])
    system_prompt: str


class ToolCall(BaseModel):
    name: str
    args: dict[str, Any]
    ok: bool
    result_preview: str
    ms: int
    evidence_id: str | None = None
    evidence_text: str | None = (
        None  # fuller result (≤ 6,000 chars) for calls that return evidence: grounding
    )


class LLMResult(BaseModel):
    node: str
    output: dict[str, Any] | None
    status: Literal["ok", "max_turns", "max_budget", "no_output", "stalled", "timeout", "error"]
    turns: int
    tool_calls: list[ToolCall]
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0  # of input_tokens, read from the provider's prompt cache
    cost_usd: float = 0.0
    model: str
    mode: Literal["live", "replay", "mock"]
    diff: str | None = None  # for nodes that edit the worktree
    error: str | None = None
