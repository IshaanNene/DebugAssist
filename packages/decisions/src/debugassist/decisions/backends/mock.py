"""Deterministic offline decider for tests, CI and scripted demos (results are labelled ``mock``).

Without overrides, every answer is a pure function of (model, state, question id, question) so
runs are reproducible. Overrides pin specific answers, e.g. for a scripted demo of BUG-002:
``{"rollback_flag": 0.93, "category": "own_code", "severity": 3}``.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any

from debugassist.core.ledger import canonical_json
from debugassist.core.settings import Mode
from debugassist.decisions.schema import (
    Answer,
    ChoiceAnswer,
    ChoiceQuestion,
    ClefRequest,
    ClefResponse,
    NoulAnswer,
    NoulQuestion,
    ScoreAnswer,
    ScoreQuestion,
    Usage,
)
from debugassist.decisions.state import estimate_tokens

type Override = float | int | str | dict[str, float]


def _unit_floats(seed: str, n: int) -> list[float]:
    out: list[float] = []
    counter = 0
    while len(out) < n:
        digest = hashlib.sha256(f"{seed}:{counter}".encode()).digest()
        out.extend(int.from_bytes(digest[i : i + 4], "big") / 2**32 for i in range(0, 32, 4))
        counter += 1
    return out[:n]


def _peaked(seed: str, n: int) -> list[float]:
    logits = [3.0 * u for u in _unit_floats(seed, n)]
    top = max(range(n), key=logits.__getitem__)
    logits[top] += 1.5  # one clear favourite, like a confident model
    z = [math.exp(x) for x in logits]
    s = sum(z)
    return [x / s for x in z]


def _from_target(options: list[str], target: str, mass: float = 0.9) -> dict[str, float]:
    rest = (1 - mass) / (len(options) - 1)
    return {o: (mass if o == target else rest) for o in options}


class MockDecider:
    name = "mock"
    mode = Mode.MOCK

    def __init__(
        self, overrides: dict[str, Override] | None = None, *, model_label: str | None = None
    ) -> None:
        self.overrides = overrides or {}
        self.model_label = model_label

    def _answer(self, seed: str, qid: str, q: NoulQuestion | ChoiceQuestion | ScoreQuestion) -> Answer:
        ov = self.overrides.get(qid)
        if isinstance(q, NoulQuestion):
            p = float(ov) if isinstance(ov, int | float) else 0.05 + 0.9 * _unit_floats(seed, 1)[0]
            return NoulAnswer(type="noul", noul=round(p, 4))
        if isinstance(q, ChoiceQuestion):
            options = list(q.criteria)
            if isinstance(ov, str):
                probs = _from_target(options, ov)
            elif isinstance(ov, dict):
                probs = {o: float(ov.get(o, 0.0)) for o in options}
            else:
                probs = dict(zip(options, _peaked(seed, len(options)), strict=True))
            choice = max(probs, key=probs.__getitem__)
            return ChoiceAnswer(
                type="choice", choice=choice, probabilities=probs, confidence=round(probs[choice], 4)
            )
        levels = [str(i) for i in range(len(q.criteria))]
        if isinstance(ov, int | float):
            probs = _from_target(levels, str(round(ov)), 0.8)
        else:
            probs = dict(zip(levels, _peaked(seed, len(levels)), strict=True))
        score = sum(int(k) * v for k, v in probs.items())
        legend: dict[str, Any] = {str(i): c for i, c in enumerate(q.criteria)}
        return ScoreAnswer(
            type="score",
            score=round(score, 4),
            legend=legend,
            probabilities=probs,
            confidence=round(max(probs.values()), 4),
        )

    async def run(self, request: ClefRequest) -> ClefResponse:
        base = canonical_json([request.model, request.state])
        answers = {
            qid: self._answer(f"{base}|{qid}|{canonical_json(q.model_dump(mode='json'))}", qid, q)
            for qid, q in request.questions.items()
        }
        tokens = estimate_tokens(request.state) + sum(
            estimate_tokens(q.model_dump(mode="json")) for q in request.questions.values()
        )
        return ClefResponse(
            model=self.model_label or request.model, answers=answers, usage=Usage(input_tokens=tokens)
        )

    def cost_usd(self, response: ClefResponse) -> float:
        return 0.0

    async def aclose(self) -> None:
        return None
