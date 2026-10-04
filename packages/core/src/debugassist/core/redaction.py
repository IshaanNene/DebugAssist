"""PII redaction for anything leaving a device or reaching an LLM / Clef.

Removes emails, phone numbers, bearer/API tokens and JWTs, payment card numbers (Luhn-checked),
and coarsens precise GPS coordinates. Applied by BugDrop server-side (in addition to the SDK's
client-side pass) and by DebugAssist before evidence reaches a model.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
BEARER = re.compile(
    r"(?i)\b(bearer|token|api[_-]?key|secret|password|authorization)\b([\"']?\s*[:=]\s*[\"']?|\s+)([A-Za-z0-9._~+/=-]{8,})"
)
KEY_PREFIXED = re.compile(r"\b(sk|pk|rk|ghp|gho|github_pat|xox[abposr])[-_][A-Za-z0-9_-]{10,}\b")
CARD = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")
PHONE = re.compile(
    r"(?<![\w.])(?:"
    r"\+\d{1,3}[\s.-]?\(?\d{1,4}\)?(?:[\s.-]?\d{2,4}){2,3}"  # international: +1 415-555-0134
    r"|\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}"  # (415) 555-0134, 415.555.0134
    r"|\d{10}"  # 4155550134
    r")(?![\w.])"
)
# lat/lng pairs with ≥4 decimals, e.g. "37.79551, -122.39372" or "lat": 37.7955
LATLNG_PAIR = re.compile(r"(-?\d{1,3}\.\d{4,})\s*,\s*(-?\d{1,3}\.\d{4,})")
COORD_KEYS = {"lat", "lng", "lon", "latitude", "longitude"}


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def _card(m: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", m.group(0))
    if 13 <= len(digits) <= 19 and _luhn_ok(digits):
        return "[card]"
    return m.group(0)


def _coarse(value: float) -> float:
    return round(value, 2)  # ~1 km: city-level, not a street address


def redact_text(text: str) -> str:
    text = JWT.sub("[token]", text)
    text = KEY_PREFIXED.sub("[token]", text)
    text = BEARER.sub(lambda m: f"{m.group(1)}{m.group(2)}[token]", text)
    text = EMAIL.sub("[email]", text)
    text = CARD.sub(_card, text)
    text = LATLNG_PAIR.sub(lambda m: f"{_coarse(float(m.group(1)))}, {_coarse(float(m.group(2)))}", text)
    return PHONE.sub("[phone]", text)


def redact(value: Any, *, text: Callable[[str], str] = redact_text) -> Any:
    """Recursively redact strings in JSON-like data; coarsen numeric lat/lng fields."""
    if isinstance(value, str):
        return text(value)
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():  # pyright: ignore[reportUnknownVariableType]
            key = str(k)  # pyright: ignore[reportUnknownArgumentType]
            if key.lower() in COORD_KEYS and isinstance(v, int | float) and not isinstance(v, bool):
                out[key] = _coarse(float(v))
            else:
                out[key] = redact(v, text=text)
        return out
    if isinstance(value, list | tuple):
        return [redact(v, text=text) for v in value]  # pyright: ignore[reportUnknownVariableType]
    return value
