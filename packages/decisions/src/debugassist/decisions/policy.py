"""Map answers to policy bands.

act (p ≥ τ_high) · escalate (τ_low < p < τ_high) · safe default (p ≤ τ_low).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from debugassist.decisions.schema import Answer, ChoiceAnswer, NoulAnswer, ScoreAnswer
from debugassist.decisions.templates import Policy


class Band(StrEnum):
    ACT = "act"
    ESCALATE = "escalate"
    SAFE_DEFAULT = "safe_default"


class Verdict(BaseModel):
    p: float
    chosen: str | None
    band: Band
    action: str


def decisive_probability(answer: Answer, n_levels: int | None = None) -> tuple[float, str | None]:
    """The probability that drives the band, and the chosen option (choice) if any.

    noul → P(yes); choice → P(chosen option); score → normalised expected level in [0, 1].
    """
    match answer:
        case NoulAnswer():
            return answer.noul, None
        case ChoiceAnswer():
            return answer.probabilities.get(answer.choice, 0.0), answer.choice
        case ScoreAnswer():
            levels = n_levels or len(answer.probabilities)
            return (answer.score / (levels - 1) if levels > 1 else 0.0), None


def apply_policy(policy: Policy, answer: Answer, n_levels: int | None = None) -> Verdict:
    p, chosen = decisive_probability(answer, n_levels)
    if p >= policy.tau_high:
        return Verdict(p=p, chosen=chosen, band=Band.ACT, action=policy.action_for(chosen))
    if p <= policy.tau_low:
        return Verdict(p=p, chosen=chosen, band=Band.SAFE_DEFAULT, action=policy.safe_default)
    return Verdict(p=p, chosen=chosen, band=Band.ESCALATE, action=policy.escalate)
