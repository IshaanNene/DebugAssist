"""Evaluation switches (SPEC §12), read from the environment so an eval run can change one thing at a time.

DA_ABLATE    comma list of decisions to switch off: D3 (log relevance), D8 (rabbit-hole monitor),
             D9 (grounding), D12 (fix localization), D14 (validation tier). Each falls back to a fixed,
             deterministic behaviour (keep evidence in order / no monitor / keep every claim / no focus /
             climb the full ladder from unit).
DA_DECIDER   routed (default: each template's own Clef model) | clef | clef-flash (one model for all) |
             llm (no Clef: the LLM decides with self-reported confidence).
DA_LLM_SEED  integer seed passed to the LLM (repeat runs per configuration).
DA_CONTEXT   full (default) | lean — how much tool output enters an agent's context (ROADMAP P15 items 2, 4, 8):
             lean adds outline tools, caps every file read at 120 lines (with a pointer to the outline), and keeps long command
             logs out of the history (an error summary and the tail come back; the full log is read on demand).
             clear replaces old tool results in the history with one-line stubs, in batches (llm/clearing.py).
             compact folds older steps into structured working notes, in batches (llm/compaction.py).
"""

from __future__ import annotations

import os
import re

KNOWN = {"D03", "D08", "D09", "D12", "D14"}


def _norm(d: str) -> str:
    m = re.fullmatch(r"[Dd]0*(\d+)", d.strip())
    return f"D{int(m.group(1)):02d}" if m else d.strip().upper()


def ablated(decision: str) -> bool:
    raw = os.environ.get("DA_ABLATE", "")
    return _norm(decision) in {_norm(x) for x in raw.split(",") if x.strip()}


def decider() -> str:
    value = os.environ.get("DA_DECIDER", "routed").strip().lower()
    if value not in {"routed", "clef", "clef-flash", "llm"}:
        raise ValueError(f"DA_DECIDER must be routed, clef, clef-flash or llm (got {value!r})")
    return value


def llm_seed() -> int | None:
    raw = os.environ.get("DA_LLM_SEED")
    return int(raw) if raw else None


def context_mode() -> str:
    value = os.environ.get("DA_CONTEXT", "full").strip().lower() or "full"
    if value not in {"full", "lean", "clear", "compact"}:
        raise ValueError(f"DA_CONTEXT must be full, lean, clear or compact (got {value!r})")
    return value


def lean() -> bool:
    return context_mode() == "lean"


def label() -> str:
    """A short name for the active configuration (for eval results)."""
    off = sorted({_norm(x) for x in os.environ.get("DA_ABLATE", "").split(",") if x.strip()})
    return (
        decider()
        + ("" if not off else "-no-" + "-".join(o.lower() for o in off))
        + ("" if context_mode() == "full" else f"-{context_mode()}")
    )
