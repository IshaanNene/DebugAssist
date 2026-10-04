import pytest

from debugassist.decisions.policy import Band, apply_policy
from debugassist.decisions.schema import ChoiceAnswer, NoulAnswer, ScoreAnswer
from debugassist.decisions.templates import Policy, get_template, load_templates


def test_all_eighteen_templates_load() -> None:
    ids = sorted(load_templates())
    assert len(ids) == 18
    assert [i.split("_")[0] for i in ids] == [f"D{n:02d}" for n in range(1, 19)]


def test_short_ids_resolve() -> None:
    assert get_template("D05").id == "D05_categorize"
    with pytest.raises(KeyError):
        get_template("D99")


def test_render_params_and_foreach() -> None:
    t = get_template("D01_triage")
    with pytest.raises(KeyError, match="teams"):
        t.render({})
    qs = t.render({"teams": {"rider-app": "client", "dispatch": "matching"}})
    assert set(qs) == {"priority", "severity", "owning_team", "customer_impacting", "worth_agent_run"}

    t7 = get_template("D07_fanout")
    qs7 = t7.render({"subagents": [{"id": "breadcrumb-analyst", "description": "rebuild the user timeline"}]})
    (qid,) = qs7
    assert qid == "spawn.breadcrumb-analyst"
    assert "rebuild the user timeline" in str(qs7[qid].instructions)


def test_missing_placeholder_does_not_crash() -> None:
    qs = get_template("D09_grounding").render({"claims": [{"id": "c1", "text": "x"}]})
    assert "<citations?>" in str(qs["supported.c1"].instructions)


P = Policy(question="q", tau_high=0.8, tau_low=0.3, act="go", escalate="ask", safe_default="stay")


@pytest.mark.parametrize(
    "p,band,action",
    [
        (0.95, Band.ACT, "go"),
        (0.8, Band.ACT, "go"),
        (0.5, Band.ESCALATE, "ask"),
        (0.3, Band.SAFE_DEFAULT, "stay"),
    ],
)
def test_noul_bands(p: float, band: Band, action: str) -> None:
    v = apply_policy(P, NoulAnswer(type="noul", noul=p))
    assert (v.band, v.action) == (band, action)


def test_choice_action_mapping() -> None:
    pol = Policy(
        question="c",
        tau_high=0.6,
        tau_low=0.2,
        act={"a": "do_a", "*": "do_other"},
        escalate="e",
        safe_default="s",
    )
    a = ChoiceAnswer(type="choice", choice="b", probabilities={"a": 0.1, "b": 0.9})
    assert apply_policy(pol, a).action == "do_other"
    a2 = ChoiceAnswer(type="choice", choice="a", probabilities={"a": 0.7, "b": 0.3})
    assert apply_policy(pol, a2).action == "do_a"


def test_score_normalised() -> None:
    s = ScoreAnswer(type="score", score=3.0, probabilities={"0": 0, "1": 0, "2": 0, "3": 1, "4": 0})
    assert apply_policy(P, s).p == pytest.approx(0.75)


def test_policy_validation() -> None:
    with pytest.raises(ValueError, match="tau_low"):
        Policy(question="q", tau_high=0.2, tau_low=0.5, act="a", escalate="e", safe_default="s")
