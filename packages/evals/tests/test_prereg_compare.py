"""Pre-registered paired comparisons: arm against arm, and arm against the no-model control."""

from __future__ import annotations

from typing import Any

from debugassist.evals import prereg


def row(
    arm: str, bug: str, seed: int, *, exact: bool, hidden: bool | None = None, control: str | None = None
) -> Any:
    return {
        "arm": arm,
        "bug": bug,
        "seed": seed,
        "run_id": "20261108-000000-x",
        "rca": "exact" if exact else "wrong",
        "hidden_tests": hidden,
        "control_rca": control,
    }


def arm(**kw: Any) -> prereg.Arm:
    return prereg.Arm.model_validate(
        {"arm": "p1-routed", "registered": "2026-11-07T00:00:00Z", "hypothesis": "h", **kw}
    )


def test_a_clear_paired_win_is_met_and_a_small_one_is_not() -> None:
    win = [row("p1-routed", f"B{i}", 1, exact=True, hidden=True) for i in range(8)]
    lose = [row("p1-baseline", f"B{i}", 1, exact=False, hidden=False) for i in range(8)]
    a = arm(comparisons=[{"metric": "hidden_tests_pass", "versus": "p1-baseline", "expect": "better"}])
    [c] = prereg.compare([a], win + lose)
    assert (c["pairs"], c["only_arm"], c["only_versus"], c["verdict"]) == (8, 8, 0, "met")
    [c] = prereg.compare([a], win[:3] + lose[:3])  # 3 of 3 discordant pairs: p = 0.25
    assert c["verdict"] == "not met" and c["p"] == 0.25


def test_no_difference_is_met_only_without_evidence_of_one() -> None:
    a = arm(comparisons=[{"metric": "rca_exact", "versus": "p1-no-clef", "expect": "no_difference"}])
    same = [row("p1-routed", "B1", 1, exact=True), row("p1-no-clef", "B1", 1, exact=True)]
    assert prereg.compare([a], same)[0]["verdict"] == "met (no evidence of a difference)"
    split = [row("p1-routed", f"B{i}", 1, exact=False) for i in range(8)]
    split += [row("p1-no-clef", f"B{i}", 1, exact=True) for i in range(8)]
    assert prereg.compare([a], split)[0]["verdict"] == "not met: p1-no-clef better"


def test_the_control_is_compared_on_the_arms_own_runs() -> None:
    a = arm(comparisons=[{"metric": "rca_exact", "versus": "control", "expect": "better"}])
    rows = [row("p1-routed", f"B{i}", 1, exact=True, control="wrong") for i in range(7)]
    rows.append(row("p1-routed", "N1", 1, exact=True, control=None))  # not-our-bug: no control
    [c] = prereg.compare([a], rows)
    assert (c["pairs"], c["only_arm"], c["verdict"]) == (7, 7, "met")
