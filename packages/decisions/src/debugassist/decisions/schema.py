"""Clef / System One wire format (Workers AI, Oct 2026) with every documented limit enforced.

Request: ``{model, state, questions, images?}``; response: ``{model, answers, usage}``. Workers AI
REST wraps the response in Cloudflare's envelope ``{"result": …, "success": …, "errors": …}``
(confirmed live 2026-10-04); :func:`parse_response` unwraps it.
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

type JSONValue = str | int | float | bool | dict[str, JSONValue] | list[JSONValue] | None

ClefModel = Literal["clef", "clef-flash"]
QUESTION_ID = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
MAX_QUESTIONS = 64
MIN_OPTIONS, MAX_OPTIONS = 2, 255
MIN_LEVELS, MAX_LEVELS = 2, 10
MAX_IMAGES = 4
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
MAX_IMAGES_TOTAL_BYTES = 8 * 1024 * 1024
MAX_BODY_BYTES = 13 * 1024 * 1024
CONTEXT_TOKENS = 65_536
IMAGE_MIME_TYPES = ("image/png", "image/jpeg", "image/webp")

# instructions and criteria values may be strings, objects or arrays (Workers AI docs).
Instructions = str | dict[str, Any] | list[Any]
OptionDescription = str | dict[str, Any] | list[Any] | None


class ClefError(Exception):
    """Base class for decision-backend errors."""


class ClefRequestError(ClefError):
    """The request was rejected (4xx other than 429) — retrying will not help."""


class ClefTransientError(ClefError):
    """Timeout, 429 or 5xx — safe to retry."""


class ClefResponseError(ClefError):
    """The backend answered, but the payload does not match the request."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _check_instructions(value: Instructions) -> Instructions:
    if isinstance(value, str) and not value.strip():
        raise ValueError("instructions must not be empty (required on Workers AI)")
    if not value:
        raise ValueError("instructions must not be empty (required on Workers AI)")
    return value


class NoulQuestion(_Strict):
    """Yes/no question; the answer is P(yes)."""

    type: Literal["noul"] = "noul"
    instructions: Instructions
    criteria: dict[Literal["true", "false"], OptionDescription] | None = None

    _v = field_validator("instructions")(_check_instructions)


class ChoiceQuestion(_Strict):
    """Pick one of 2–255 options; the answer is a distribution over options."""

    type: Literal["choice"] = "choice"
    instructions: Instructions
    criteria: dict[str, OptionDescription]

    _v = field_validator("instructions")(_check_instructions)

    @field_validator("criteria")
    @classmethod
    def _options(cls, v: dict[str, OptionDescription]) -> dict[str, OptionDescription]:
        if not MIN_OPTIONS <= len(v) <= MAX_OPTIONS:
            raise ValueError(f"choice needs {MIN_OPTIONS}–{MAX_OPTIONS} options, got {len(v)}")
        if any(not k.strip() for k in v):
            raise ValueError("choice option names must be non-empty")
        return v


class ScoreQuestion(_Strict):
    """Ordinal scale of 2–10 levels; index 0 is the lowest level."""

    type: Literal["score"] = "score"
    instructions: Instructions
    criteria: list[str | dict[str, Any] | list[Any]]

    _v = field_validator("instructions")(_check_instructions)

    @field_validator("criteria")
    @classmethod
    def _levels(cls, v: list[Any]) -> list[Any]:
        if not MIN_LEVELS <= len(v) <= MAX_LEVELS:
            raise ValueError(f"score needs {MIN_LEVELS}–{MAX_LEVELS} levels, got {len(v)}")
        return v


Question = Annotated[NoulQuestion | ChoiceQuestion | ScoreQuestion, Field(discriminator="type")]


class Base64Image(_Strict):
    content_type: Literal["image/png", "image/jpeg", "image/webp"]
    base64: str


ImagePayload = str | Base64Image  # data URL or {"content_type", "base64"}; no remote URLs


def validate_question_ids(questions: dict[str, Any]) -> None:
    if not 1 <= len(questions) <= MAX_QUESTIONS:
        raise ValueError(f"1–{MAX_QUESTIONS} questions per call, got {len(questions)}")
    bad = [q for q in questions if not QUESTION_ID.match(q)]
    if bad:
        raise ValueError(f"invalid question ids (must match {QUESTION_ID.pattern}): {bad}")


class ClefRequest(_Strict):
    model: ClefModel
    state: JSONValue
    questions: dict[str, Question]
    images: list[ImagePayload] | None = None

    @field_validator("questions")
    @classmethod
    def _questions(cls, v: dict[str, Question]) -> dict[str, Question]:
        validate_question_ids(v)
        return v

    @field_validator("images")
    @classmethod
    def _images(cls, v: list[ImagePayload] | None) -> list[ImagePayload] | None:
        if v is None:
            return v
        if len(v) > MAX_IMAGES:
            raise ValueError(f"at most {MAX_IMAGES} images, got {len(v)}")
        for img in v:
            if isinstance(img, str):
                if img.startswith(("http://", "https://")):
                    raise ValueError("remote image URLs are not supported; send data URLs")
                if not img.startswith(tuple(f"data:{m};base64," for m in IMAGE_MIME_TYPES)):
                    raise ValueError("images must be PNG/JPEG/WebP data URLs")
        # Byte/pixel limits are enforced (with auto-resize) in images.prepare_images().
        return v

    @model_validator(mode="after")
    def _state_present(self) -> ClefRequest:
        if self.state is None or self.state in ("", {}, []):
            raise ValueError("state is required")
        return self

    def body(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)

    def body_bytes(self) -> bytes:
        raw = json.dumps(self.body(), separators=(",", ":"), ensure_ascii=False).encode()
        if len(raw) > MAX_BODY_BYTES:
            raise ClefRequestError(f"request body is {len(raw)} bytes; limit is {MAX_BODY_BYTES}")
        return raw


class NoulAnswer(BaseModel):
    type: Literal["noul"]
    noul: float = Field(ge=0.0, le=1.0)


class ChoiceAnswer(BaseModel):
    type: Literal["choice"]
    choice: str
    probabilities: dict[str, float]
    confidence: float | None = None


class ScoreAnswer(BaseModel):
    type: Literal["score"]
    score: float
    legend: dict[str, Any] = Field(default_factory=dict[str, Any])
    probabilities: dict[str, float]
    confidence: float | None = None


Answer = Annotated[NoulAnswer | ChoiceAnswer | ScoreAnswer, Field(discriminator="type")]


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class ClefResponse(BaseModel):
    model: str
    answers: dict[str, Answer]
    usage: Usage = Field(default_factory=Usage)

    def check_against(self, request: ClefRequest) -> None:
        """Every question answered, with the right type and option set."""
        missing = set(request.questions) - set(self.answers)
        if missing:
            raise ClefResponseError(f"unanswered questions: {sorted(missing)}")
        for qid, q in request.questions.items():
            a = self.answers[qid]
            if a.type != q.type:
                raise ClefResponseError(f"{qid}: asked {q.type}, got {a.type}")
            if isinstance(q, ChoiceQuestion) and isinstance(a, ChoiceAnswer):  # noqa: SIM102
                if set(a.probabilities) != set(q.criteria):
                    raise ClefResponseError(f"{qid}: option set mismatch")
            if isinstance(q, ScoreQuestion) and isinstance(a, ScoreAnswer):  # noqa: SIM102
                if set(a.probabilities) != {str(i) for i in range(len(q.criteria))}:
                    raise ClefResponseError(f"{qid}: level set mismatch")


def parse_response(raw: dict[str, Any]) -> ClefResponse:
    """Unwrap Cloudflare's REST envelope when present and validate the payload."""
    if "result" in raw and ("success" in raw or "errors" in raw):
        if raw.get("success") is False:
            raise ClefRequestError(f"Workers AI error: {raw.get('errors')}")
        raw = raw["result"]
    try:
        return ClefResponse.model_validate(raw)
    except ValueError as exc:
        raise ClefResponseError(f"malformed Clef response: {exc}") from exc
