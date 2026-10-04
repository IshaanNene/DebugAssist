from typing import Any

import pytest
from pydantic import ValidationError

from debugassist.decisions.schema import (
    ClefRequest,
    ClefRequestError,
    ClefResponseError,
    parse_response,
)


def req(**kw: Any) -> ClefRequest:
    base: dict[str, Any] = {
        "model": "clef",
        "state": "x",
        "questions": {"q": {"type": "noul", "instructions": "?"}},
    }
    base.update(kw)
    return ClefRequest.model_validate(base)


def noul(n: int) -> dict[str, Any]:
    return {f"q{i}": {"type": "noul", "instructions": "?"} for i in range(n)}


def test_basic_request_round_trips(basic_questions: dict[str, Any]) -> None:
    r = req(questions=basic_questions)
    body = r.body()
    assert body["model"] == "clef" and "images" not in body
    assert body["questions"]["severity"]["criteria"][0] == "cosmetic"


@pytest.mark.parametrize("model", ["clef", "clef-flash"])
def test_models_accepted(model: str) -> None:
    assert req(model=model).model == model


def test_unknown_model_rejected() -> None:
    with pytest.raises(ValidationError):
        req(model="clef-pro")


@pytest.mark.parametrize("n,ok", [(0, False), (1, True), (64, True), (65, False)])
def test_question_count_limits(n: int, ok: bool) -> None:
    if ok:
        req(questions=noul(n))
    else:
        with pytest.raises(ValidationError, match="questions per call"):
            req(questions=noul(n))


@pytest.mark.parametrize("qid", ["a b", "x" * 101, "q/1", ""])
def test_bad_question_ids(qid: str) -> None:
    with pytest.raises(ValidationError):
        req(questions={qid: {"type": "noul", "instructions": "?"}})


def test_good_question_ids() -> None:
    req(
        questions={
            "a.b-c_D9": {"type": "noul", "instructions": "?"},
            "x" * 100: {"type": "noul", "instructions": "?"},
        }
    )


@pytest.mark.parametrize("n,ok", [(1, False), (2, True), (255, True), (256, False)])
def test_choice_option_limits(n: int, ok: bool) -> None:
    q = {"c": {"type": "choice", "instructions": "?", "criteria": {f"o{i}": None for i in range(n)}}}
    if ok:
        req(questions=q)
    else:
        with pytest.raises(ValidationError, match="options"):
            req(questions=q)


@pytest.mark.parametrize("n,ok", [(1, False), (2, True), (10, True), (11, False)])
def test_score_level_limits(n: int, ok: bool) -> None:
    q = {"s": {"type": "score", "instructions": "?", "criteria": [f"l{i}" for i in range(n)]}}
    if ok:
        req(questions=q)
    else:
        with pytest.raises(ValidationError, match="levels"):
            req(questions=q)


def test_instructions_required_and_non_empty() -> None:
    with pytest.raises(ValidationError):
        req(questions={"q": {"type": "noul"}})
    with pytest.raises(ValidationError):
        req(questions={"q": {"type": "noul", "instructions": "  "}})


def test_instructions_and_criteria_may_be_structured() -> None:
    req(
        questions={
            "c": {
                "type": "choice",
                "instructions": {"task": "pick", "notes": ["a", "b"]},
                "criteria": {"a": {"desc": "x"}, "b": None},
            }
        }
    )


def test_noul_criteria_keys() -> None:
    req(questions={"q": {"type": "noul", "instructions": "?", "criteria": {"true": "y", "false": "n"}}})
    with pytest.raises(ValidationError):
        req(questions={"q": {"type": "noul", "instructions": "?", "criteria": {"maybe": "?"}}})


def test_state_required() -> None:
    empties: list[Any] = ["", {}, []]
    for empty in empties:
        with pytest.raises(ValidationError, match="state"):
            req(state=empty)


def test_images_limits() -> None:
    url = "data:image/png;base64,iVBORw0KGgo="
    req(images=[url] * 4)
    req(images=[{"content_type": "image/webp", "base64": "AAAA"}])
    with pytest.raises(ValidationError, match="at most 4"):
        req(images=[url] * 5)
    with pytest.raises(ValidationError, match="remote"):
        req(images=["https://example.com/a.png"])
    with pytest.raises(ValidationError, match="PNG/JPEG/WebP"):
        req(images=["data:image/gif;base64,AAAA"])


def test_body_size_limit() -> None:
    big = req(state="x" * (13 * 1024 * 1024))
    with pytest.raises(ClefRequestError, match="request body"):
        big.body_bytes()


def test_parse_live_fixture_unwraps_envelope(
    clef_fixture: dict[str, Any], basic_questions: dict[str, Any]
) -> None:
    resp = parse_response(clef_fixture)
    assert resp.model == "clef"
    assert resp.usage.input_tokens == 402
    resp.check_against(req(questions=basic_questions))


def test_parse_unwrapped_payload(clef_fixture: dict[str, Any]) -> None:
    assert parse_response(clef_fixture["result"]).model == "clef"


def test_error_envelope_raises() -> None:
    with pytest.raises(ClefRequestError, match="Workers AI error"):
        parse_response({"result": None, "success": False, "errors": [{"code": 5006, "message": "bad"}]})


def test_malformed_payload_raises() -> None:
    with pytest.raises(ClefResponseError):
        parse_response({"model": "clef", "answers": {"q": {"type": "noul", "noul": 1.7}}})


def test_check_against_detects_mismatches(
    clef_fixture: dict[str, Any], basic_questions: dict[str, Any]
) -> None:
    resp = parse_response(clef_fixture)
    extra = dict(basic_questions, other={"type": "noul", "instructions": "?"})
    with pytest.raises(ClefResponseError, match="unanswered"):
        resp.check_against(req(questions=extra))
    wrong_type = dict(
        basic_questions, needs_code_change={"type": "score", "instructions": "?", "criteria": ["a", "b"]}
    )
    with pytest.raises(ClefResponseError, match="asked score"):
        resp.check_against(req(questions=wrong_type))
    wrong_opts = dict(basic_questions)
    wrong_opts["category"] = {
        "type": "choice",
        "instructions": "?",
        "criteria": {"own_code": None, "x": None},
    }
    with pytest.raises(ClefResponseError, match="option set"):
        resp.check_against(req(questions=wrong_opts))
