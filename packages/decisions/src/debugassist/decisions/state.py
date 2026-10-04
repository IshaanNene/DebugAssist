"""Compact, typed decision state with the decisive evidence first, under a token budget.

Clef truncates long state on its own; we prefer to choose what is dropped. Sections are added in
priority order; long strings are trimmed head+tail; sections that no longer fit are dropped and
listed under ``_omitted`` so the model knows evidence exists that it cannot see.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, cast

from debugassist.core.ledger import canonical_json

CHARS_PER_TOKEN = 3.2  # conservative for JSON-heavy text; corrected later by usage.input_tokens


def estimate_tokens(value: Any) -> int:
    text = value if isinstance(value, str) else canonical_json(value)
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def trim_text(text: str, max_tokens: int) -> str:
    max_chars = int(max_tokens * CHARS_PER_TOKEN)
    if len(text) <= max_chars:
        return text
    marker = f" …[{len(text) - max_chars} chars trimmed]… "
    keep = max(0, max_chars - len(marker))
    head = keep * 2 // 3
    return text[:head] + marker + text[len(text) - (keep - head) :]


def _trim_value(value: Any, max_tokens: int) -> Any:
    if isinstance(value, str):
        return trim_text(value, max_tokens)
    if isinstance(value, list) and estimate_tokens(value) > max_tokens:
        items: list[Any] = []
        for item in value:  # pyright: ignore[reportUnknownVariableType]
            if estimate_tokens([*items, item]) > max_tokens:
                items.append(f"…{len(value) - len(items)} more items omitted")  # pyright: ignore[reportUnknownArgumentType]
                break
            items.append(item)
        return cast(Any, items)
    if isinstance(value, dict) and estimate_tokens(value) > max_tokens:
        per = max(16, max_tokens // max(1, len(value)))  # pyright: ignore[reportUnknownArgumentType]
        return {k: _trim_value(v, per) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType]
    return cast(Any, value)


@dataclass
class CompactState:
    """Ordered evidence sections. Lower ``priority`` = more decisive = kept first."""

    sections: list[tuple[int, str, Any]] = field(default_factory=list[tuple[int, str, Any]])

    def add(self, name: str, value: Any, *, priority: int = 50) -> CompactState:
        if value not in (None, "", [], {}):
            self.sections.append((priority, name, value))
        return self

    def render(self, budget_tokens: int) -> dict[str, Any]:
        out: dict[str, Any] = {}
        omitted: list[str] = []
        used = 0
        for _, name, value in sorted(self.sections, key=lambda s: s[0]):
            remaining = budget_tokens - used
            cost = estimate_tokens({name: value})
            if cost <= remaining:
                out[name] = value
                used += cost
            elif remaining > 64:
                # JSON escaping inflates text, so shrink the target until the rendered section fits.
                target = remaining - 16
                trimmed = _trim_value(value, target)
                while estimate_tokens({name: trimmed}) > remaining and target > 32:
                    target = int(target * 0.8)
                    trimmed = _trim_value(value, target)
                out[name] = trimmed
                used += estimate_tokens({name: trimmed})
            else:
                omitted.append(name)
        if omitted:
            out["_omitted"] = omitted
        return out


def fit_state(state: Any, budget_tokens: int) -> Any:
    """Apply the token budget to any state value."""
    if isinstance(state, CompactState):
        return state.render(budget_tokens)
    if estimate_tokens(state) <= budget_tokens:
        return state
    return _trim_value(state, budget_tokens)
