"""Versioned decision templates (``packages/decisions/templates/*.yaml``) and their rendering.

A template declares questions in Clef's wire format plus three extensions resolved at call time:

* ``criteria: $name`` — options supplied by the caller (e.g. owning teams from the service catalog).
* ``foreach: name`` — one question per item of a caller-supplied list; ids become ``<qid>.<item id>``
  and ``{field}`` placeholders in ``instructions`` are filled from the item.
* ``two_stage`` — for large candidate sets: per-candidate nouls, then a choice over the top-K.
"""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from debugassist.decisions.schema import QUESTION_ID, ClefModel, Question

_PACKAGED = Path(__file__).parent / "template_files"  # wheel / PEX builds
_REPO = Path(__file__).resolve().parents[3] / "templates"
QUESTION_ADAPTER: TypeAdapter[Question] = TypeAdapter(Question)


class Item(BaseModel):
    """A foreach item. ``id`` must be usable inside a question id; other fields fill placeholders."""

    model_config = ConfigDict(extra="allow")
    id: str

    def fields(self) -> dict[str, Any]:
        return self.model_dump()


class QuestionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["noul", "choice", "score"]
    instructions: str | dict[str, Any] | list[Any]
    criteria: str | dict[str, Any] | list[Any] | None = None  # "$param" → supplied at call time
    foreach: str | None = None


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str
    tau_high: float = Field(ge=0, le=1)
    tau_low: float = Field(ge=0, le=1)
    act: str | dict[str, str]  # dict: chosen option → action; "*" = any other option
    escalate: str
    safe_default: str
    per_item: bool = False

    @model_validator(mode="after")
    def _ordered(self) -> Policy:
        if self.tau_low > self.tau_high:
            raise ValueError("tau_low must be <= tau_high")
        return self

    def action_for(self, chosen: str | None) -> str:
        if isinstance(self.act, str):
            return self.act
        if chosen is not None and chosen in self.act:
            return self.act[chosen]
        return self.act.get("*", self.safe_default)


class TwoStage(BaseModel):
    item_question: str
    choice_question: str
    top_k: int = Field(default=10, ge=2, le=254)
    max_direct: int = Field(default=64, ge=2, le=254)


class Template(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    version: int = Field(ge=1)
    stage: str
    description: str
    model: ClefModel
    state_budget_tokens: int = Field(default=6000, ge=256, le=60_000)
    questions: dict[str, QuestionSpec]
    policy: Policy
    two_stage: TwoStage | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Template:
        if self.policy.question not in self.questions:
            raise ValueError(f"{self.id}: policy.question {self.policy.question!r} is not a question")
        if self.policy.per_item != (self.questions[self.policy.question].foreach is not None):
            raise ValueError(f"{self.id}: policy.per_item must match whether the question uses foreach")
        for qid in self.questions:
            if not QUESTION_ID.match(qid):
                raise ValueError(f"{self.id}: bad question id {qid!r}")
        if self.two_stage and {self.two_stage.item_question, self.two_stage.choice_question} - set(
            self.questions
        ):
            raise ValueError(f"{self.id}: two_stage refers to unknown questions")
        return self

    def params(self) -> set[str]:
        out: set[str] = set()
        for q in self.questions.values():
            if isinstance(q.criteria, str):
                out.add(q.criteria.removeprefix("$"))
            if q.foreach:
                out.add(q.foreach)
        return out

    def render(
        self, params: dict[str, Any] | None = None, *, only: set[str] | None = None
    ) -> dict[str, Question]:
        """Produce wire-format questions. ``only`` restricts to some template question ids."""
        params = params or {}
        out: dict[str, Question] = {}
        for qid, spec in self.questions.items():
            if only is not None and qid not in only:
                continue
            criteria = spec.criteria
            if isinstance(criteria, str):
                name = criteria.removeprefix("$")
                if name not in params:
                    raise KeyError(f"{self.id}.{qid} needs parameter {name!r}")
                criteria = params[name]
            base: dict[str, Any] = {"type": spec.type, "instructions": spec.instructions}
            if criteria is not None:
                base["criteria"] = criteria
            if spec.foreach is None:
                out[qid] = QUESTION_ADAPTER.validate_python(base)
                continue
            if spec.foreach not in params:
                raise KeyError(f"{self.id}.{qid} needs foreach list {spec.foreach!r}")
            for raw in params[spec.foreach]:
                item = raw if isinstance(raw, Item) else Item.model_validate(raw)
                q = dict(base)
                if isinstance(spec.instructions, str):
                    q["instructions"] = spec.instructions.format_map(_Defaulting(item.fields()))
                out[f"{qid}.{item.id}"] = QUESTION_ADAPTER.validate_python(q)
        return out


class _Defaulting(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return f"<{key}?>"


def templates_dir() -> Path:
    if _PACKAGED.is_dir():
        return _PACKAGED
    root = os.environ.get("DEBUGASSIST_ROOT")  # a packaged run with the checkout mounted
    if root and (Path(root) / "packages" / "decisions" / "templates").is_dir():
        return Path(root) / "packages" / "decisions" / "templates"
    return _REPO


@cache
def load_templates(directory: Path | None = None) -> dict[str, Template]:
    directory = directory or templates_dir()
    templates: dict[str, Template] = {}
    for path in sorted(directory.glob("*.yaml")):
        t = Template.model_validate(yaml.safe_load(path.read_text()))
        if t.id != path.stem:
            raise ValueError(f"{path.name}: id {t.id!r} must match the file name")
        templates[t.id] = t
    return templates


def get_template(decision_id: str) -> Template:
    templates = load_templates()
    if decision_id in templates:
        return templates[decision_id]
    matches = [t for k, t in templates.items() if k.split("_", 1)[0] == decision_id]  # "D05" → D05_*
    if len(matches) == 1:
        return matches[0]
    raise KeyError(f"unknown decision template {decision_id!r}; known: {sorted(templates)}")
