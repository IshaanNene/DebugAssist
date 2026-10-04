"""DecisionEngine: template → compact state → backend call(s) → policy band → ledger row.

Clef never acts: the engine returns a :class:`Decision` (probabilities, chosen values, band,
suggested action); pipeline code decides what to do with it, behind the write-policy gate.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, cast

from pydantic import BaseModel, Field

from debugassist.core.ledger import DecisionRow, Ledger, content_hash
from debugassist.core.settings import Mode
from debugassist.decisions.backends.base import DecisionBackend
from debugassist.decisions.images import ImageSource, prepare_images
from debugassist.decisions.policy import Band, Verdict, apply_policy
from debugassist.decisions.resilience import FallbackBackend
from debugassist.decisions.schema import (
    MAX_QUESTIONS,
    Answer,
    ChoiceAnswer,
    ClefModel,
    ClefRequest,
    ClefResponse,
    ImagePayload,
    NoulAnswer,
    Question,
    ScoreAnswer,
    ScoreQuestion,
)
from debugassist.decisions.state import estimate_tokens, fit_state
from debugassist.decisions.templates import Item, Template, get_template


class RunContext(BaseModel):
    run_id: str | None = None
    issue_id: str | None = None


class Decision(BaseModel):
    decision_id: str
    template_version: int
    model: str
    backend: str
    mode: Mode
    answers: dict[str, Answer]
    probabilities: dict[str, dict[str, float]]
    chosen: dict[str, str | float | bool]
    # Policy result for the template's policy question (None for per-item policies).
    p: float | None = None
    confidence: float | None = None
    band: Band | None = None
    action: str | None = None
    items: dict[str, Verdict] = Field(default_factory=dict[str, Verdict])
    latency_ms: int
    input_tokens: int
    output_tokens: int = 0
    cost_usd: float
    n_calls: int
    state_tokens_est: int
    fallback_reason: str | None = None
    note: str | None = None
    ledger_id: str | None = None
    second_opinion: Decision | None = None


def _probabilities(answer: Answer) -> dict[str, float]:
    match answer:
        case NoulAnswer():
            return {"true": answer.noul, "false": round(1 - answer.noul, 6)}
        case ChoiceAnswer() | ScoreAnswer():
            return dict(answer.probabilities)


def _chosen(answer: Answer) -> str | float | bool:
    match answer:
        case NoulAnswer():
            return answer.noul >= 0.5
        case ChoiceAnswer():
            return answer.choice
        case ScoreAnswer():
            return answer.score


def _criteria_from_items(value: Any) -> Any:
    """A list of items passed for a ``criteria: $param`` becomes {id: description}."""
    if isinstance(value, list) and value and all(isinstance(v, dict | Item) for v in value):  # pyright: ignore[reportUnknownVariableType]
        out: dict[str, Any] = {}
        for raw in value:  # pyright: ignore[reportUnknownVariableType]
            item = raw if isinstance(raw, Item) else Item.model_validate(raw)
            fields = item.fields()
            out[item.id] = fields.get("description") or fields.get("summary")
        return out
    return cast(Any, value)


class DecisionEngine:
    def __init__(
        self,
        backend: DecisionBackend,
        *,
        ledger: Ledger | None = None,
        second_opinion: DecisionBackend | None = None,
        model_override: ClefModel | None = None,
        max_concurrency: int = 4,
    ) -> None:
        self.backend = backend
        self.ledger = ledger
        self.second_opinion = second_opinion
        self.model_override: ClefModel | None = model_override
        self._sem = asyncio.Semaphore(max_concurrency)

    async def decide(
        self,
        decision_id: str,
        state: Any,
        images: list[ImageSource] | None = None,
        *,
        params: dict[str, Any] | None = None,
        ctx: RunContext | None = None,
        model: ClefModel | None = None,
    ) -> Decision:
        template = get_template(decision_id)
        params = dict(params or {})
        if template.two_stage is None:  # two-stage templates convert candidates themselves
            params = {
                k: _criteria_from_items(v) if self._is_criteria_param(template, k) else v
                for k, v in params.items()
            }
        ctx = ctx or RunContext()
        chosen_model: ClefModel = template.model
        if model is not None:
            chosen_model = model
        elif self.model_override is not None:
            chosen_model = self.model_override
        fitted = fit_state(state, template.state_budget_tokens)
        image_urls = prepare_images(images) if images else None

        if template.two_stage is not None:
            return await self._two_stage(template, fitted, image_urls, params, ctx, chosen_model)
        questions = template.render(params)
        return await self._run(template, fitted, image_urls, questions, ctx, chosen_model)

    @staticmethod
    def _is_criteria_param(template: Template, name: str) -> bool:
        return any(q.criteria == f"${name}" and q.foreach is None for q in template.questions.values())

    async def _call_chunks(
        self,
        model: ClefModel,
        state: Any,
        images: list[str] | None,
        questions: dict[str, Question],
        backend: DecisionBackend,
    ) -> tuple[dict[str, Answer], int, int, int, float, str | None, str]:
        """Send ≤64 questions per call (concurrently); merge answers and usage."""
        ids = list(questions)
        chunks = [ids[i : i + MAX_QUESTIONS] for i in range(0, len(ids), MAX_QUESTIONS)]

        async def one(chunk: list[str]) -> tuple[ClefResponse, float, str | None]:
            req = ClefRequest(
                model=model,
                state=state,
                questions={q: questions[q] for q in chunk},
                images=cast(list[ImagePayload] | None, images),
            )
            async with self._sem:
                resp = await backend.run(req)
                reason = backend.last_fallback_reason if isinstance(backend, FallbackBackend) else None
                return resp, backend.cost_usd(resp), reason

        results = await asyncio.gather(*(one(c) for c in chunks))
        answers: dict[str, Answer] = {}
        tokens_in = tokens_out = 0
        cost = 0.0
        reasons = [r for _, _, r in results if r]
        for resp, c, _ in results:
            answers.update(resp.answers)
            tokens_in += resp.usage.input_tokens
            tokens_out += resp.usage.output_tokens
            cost += c
        served_by = results[0][0].model
        return answers, len(chunks), tokens_in, tokens_out, cost, (reasons[0] if reasons else None), served_by

    def _backend_name(self, backend: DecisionBackend) -> tuple[str, Mode]:
        if isinstance(backend, FallbackBackend):
            return backend.last_backend.name, backend.last_backend.mode
        return backend.name, backend.mode

    async def _run(
        self,
        template: Template,
        state: Any,
        images: list[str] | None,
        questions: dict[str, Question],
        ctx: RunContext,
        model: ClefModel,
        *,
        backend: DecisionBackend | None = None,
        parent_id: str | None = None,
        extra: tuple[dict[str, Answer], int, int, int, float] | None = None,
    ) -> Decision:
        backend = backend or self.backend
        t0 = time.perf_counter()
        answers, n_calls, t_in, t_out, cost, fallback, served_by = await self._call_chunks(
            model, state, images, questions, backend
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        if extra is not None:  # stage-1 results of a two-stage decision
            answers = {**extra[0], **answers}
            n_calls += extra[1]
            t_in += extra[2]
            t_out += extra[3]
            cost += extra[4]
        all_questions = questions
        decision = self._verdict(template, answers, all_questions)
        backend_name, mode = self._backend_name(backend)
        note = getattr(getattr(backend, "last_backend", backend), "last_note", None)
        d = Decision(
            decision_id=template.id,
            template_version=template.version,
            model=served_by,
            backend=backend_name,
            mode=mode,
            answers=answers,
            probabilities={q: _probabilities(a) for q, a in answers.items()},
            chosen={q: _chosen(a) for q, a in answers.items()},
            latency_ms=latency_ms,
            input_tokens=t_in,
            output_tokens=t_out,
            cost_usd=round(cost, 8),
            n_calls=n_calls,
            state_tokens_est=estimate_tokens(state),
            fallback_reason=fallback,
            note=note if isinstance(note, str) else None,
            **decision,
        )
        if (
            d.band is Band.ESCALATE
            and template.policy.escalate == "llm"
            and self.second_opinion is not None
            and parent_id is None
        ):
            d.ledger_id = await self._record(template, state, questions, images, d, ctx, parent_id)
            second = await self._run(
                template,
                state,
                images,
                questions,
                ctx,
                model,
                backend=self.second_opinion,
                parent_id=d.ledger_id,
            )
            d.second_opinion = second
            d.band = second.band if second.band is not Band.ESCALATE else Band.ESCALATE
            d.action = second.action if second.band is not Band.ESCALATE else "human"
            return d
        d.ledger_id = await self._record(template, state, questions, images, d, ctx, parent_id)
        return d

    def _verdict(
        self, template: Template, answers: dict[str, Answer], questions: dict[str, Question]
    ) -> dict[str, Any]:
        policy = template.policy
        if policy.per_item:
            prefix = policy.question + "."
            items = {
                qid.removeprefix(prefix): apply_policy(policy, a, self._levels(questions.get(qid)))
                for qid, a in answers.items()
                if qid.startswith(prefix)
            }
            return {"items": items}
        answer = answers[policy.question]
        v = apply_policy(policy, answer, self._levels(questions.get(policy.question)))
        conf = getattr(answer, "confidence", None)
        if conf is None:
            conf = max(v.p, 1 - v.p) if isinstance(answer, NoulAnswer) else v.p
        return {"p": round(v.p, 6), "confidence": round(conf, 6), "band": v.band, "action": v.action}

    @staticmethod
    def _levels(q: Question | None) -> int | None:
        return len(q.criteria) if isinstance(q, ScoreQuestion) else None

    async def _two_stage(
        self,
        template: Template,
        state: Any,
        images: list[str] | None,
        params: dict[str, Any],
        ctx: RunContext,
        model: ClefModel,
    ) -> Decision:
        assert template.two_stage is not None
        ts = template.two_stage
        item_spec = template.questions[ts.item_question]
        assert item_spec.foreach is not None
        candidates = [c if isinstance(c, Item) else Item.model_validate(c) for c in params[item_spec.foreach]]
        include_none = isinstance(template.policy.act, dict) and "none" in template.policy.act
        extra = None
        if len(candidates) > ts.max_direct:
            stage1 = template.render({item_spec.foreach: candidates}, only={ts.item_question})
            answers, n, t_in, t_out, cost, _, _ = await self._call_chunks(
                model, state, images, stage1, self.backend
            )
            prefix = ts.item_question + "."

            def score(c: Item) -> float:
                a = answers.get(prefix + c.id)
                return a.noul if isinstance(a, NoulAnswer) else 0.0

            candidates = sorted(candidates, key=score, reverse=True)[: ts.top_k]
            extra = (answers, n, t_in, t_out, cost)
        options: dict[str, Any] = _criteria_from_items(candidates)
        if include_none:
            options["none"] = "none of these candidates"
        choice_param = template.questions[ts.choice_question].criteria
        assert isinstance(choice_param, str)
        questions = template.render({choice_param.removeprefix("$"): options}, only={ts.choice_question})
        return await self._run(template, state, images, questions, ctx, model, extra=extra)

    async def _record(
        self,
        template: Template,
        state: Any,
        questions: dict[str, Question],
        images: list[str] | None,
        d: Decision,
        ctx: RunContext,
        parent_id: str | None,
    ) -> str | None:
        if self.ledger is None:
            return None
        return await self.ledger.record(
            DecisionRow(
                run_id=ctx.run_id,
                issue_id=ctx.issue_id,
                parent_id=parent_id,
                decision_id=d.decision_id,
                template_version=d.template_version,
                backend=d.backend,
                model=d.model,
                mode=d.mode.value,
                state=state,
                state_hash=content_hash(state),
                questions={k: v.model_dump(mode="json") for k, v in questions.items()},
                n_images=len(images or []),
                answers={k: v.model_dump(mode="json") for k, v in d.answers.items()},
                chosen=d.chosen,
                confidence=d.confidence if d.confidence is not None else -1.0,
                band=d.band.value if d.band else "per_item",
                action=d.action or "per_item",
                latency_ms=d.latency_ms,
                input_tokens=d.input_tokens,
                output_tokens=d.output_tokens,
                cost_usd=d.cost_usd,
                n_calls=d.n_calls,
                fallback_reason=d.fallback_reason,
            )
        )

    async def aclose(self) -> None:
        await self.backend.aclose()
        if self.second_opinion is not None and self.second_opinion is not self.backend:
            await self.second_opinion.aclose()
