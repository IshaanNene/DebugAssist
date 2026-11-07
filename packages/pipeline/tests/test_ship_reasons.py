"""Ship outcomes carry a typed reason, and what the run tells a maintainer is built from it.

The review that prompted this: an own_code root cause whose reproduction was not verified became `rca_only`, and
the GitHub App comment then said the cause was "outside this repository's code". D16's `escalate` was also
overwritten by `rca_only` whenever there was no verified reproduction.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from debugassist.core.policy import Policy, PolicyGate
from debugassist.decisions.policy import Band
from debugassist.pipeline import nodes
from debugassist.pipeline.nodes.ship import explain
from debugassist.pipeline.state import FixPlan, Mitigation, RunState

FIXTURE = Path(__file__).parent / "fixtures" / "run_state.json"
OUTSIDE = "outside this repository"


class D16:
    def __init__(self, action: str) -> None:
        self.action = action

    async def decide(self, decision_id: str, cs: Any, **kw: Any) -> Any:
        return SimpleNamespace(
            p=0.9, band=Band.ACT, action=self.action, chosen={"risk": 0.1}, ledger_id="d16"
        )


def state(category: str, repro: bool | None, *, tests_only: bool = False) -> RunState:
    """The fixture run (own_code, routeV2) with its category and reproduction changed. repro=None: no fix attempt,
    as for a routed category, which never reaches the fix node."""
    s = RunState.model_validate(json.loads(FIXTURE.read_text()))
    assert s.rca and s.rca.output and s.issue
    s.rca.output.category = category  # pyright: ignore[reportAttributeAccessIssue]
    s.ship = None
    if repro is None:
        s.fix_attempts = []
    else:
        s.fix_attempts[-1].repro_verified = repro
        if tests_only:
            s.fix_attempts[-1].files = [f for f in s.fix_attempts[-1].files if f.startswith("test/")]
    return s


async def ship(s: RunState, d16: str, tmp_path: Path) -> Any:
    assert s.issue
    deps: Any = SimpleNamespace(
        engine=D16(d16), gate=PolicyGate(Policy(repos=[s.issue.gh_repo]), tmp_path / "audit.jsonl")
    )
    out = (await nodes.ship_gate(s, deps))["ship"]
    s.ship = out
    return out


# RCA category x reproduction verified x D16 action -> outcome, reason, a phrase the comment must contain.
CASES = [
    ("own_code", True, "open_pr", "open_pr", None, "ready for review"),
    ("own_code", True, "draft_pr", "draft_pr", None, "ready for review"),
    ("own_code", True, "rca_only", "rca_only", "needs_human", "maintainer's decision"),
    ("own_code", True, "escalate", "escalate", "needs_human", "maintainer's decision"),
    ("own_code", False, "open_pr", "rca_only", "repro_failed", "no test reproduced"),
    ("own_code", False, "draft_pr", "rca_only", "repro_failed", "no test reproduced"),
    ("own_code", False, "rca_only", "rca_only", "repro_failed", "no test reproduced"),
    ("own_code", False, "escalate", "escalate", "repro_failed", "maintainer's decision"),
    ("third_party_lib", None, "open_pr", "rca_only", "not_our_code", "(third party lib)"),
    ("infra", None, "escalate", "rca_only", "not_our_code", "(infra)"),
    ("device_os", None, "open_pr", "rca_only", "not_our_code", "(device os)"),
    ("not_a_bug", None, "open_pr", "rca_only", "not_our_code", "(not a bug)"),
    ("own_code", None, "open_pr", "rca_only", "no_fix", "did not produce an actionable"),
]


@pytest.mark.parametrize(("category", "repro", "d16", "outcome", "reason", "phrase"), CASES)
async def test_outcome_reason_and_comment(
    tmp_path: Path, category: str, repro: bool | None, d16: str, outcome: str, reason: str | None, phrase: str
) -> None:
    s = state(category, repro)
    got = await ship(s, d16, tmp_path)
    assert (got.outcome, got.reason) == (outcome, reason)
    pr = "https://github.com/acme/widgets/pull/5" if outcome in ("open_pr", "draft_pr") else None
    comment = nodes.app_comment(s, pr)
    assert phrase in comment
    assert (OUTSIDE in comment) == (reason == "not_our_code")  # only a routed category says "outside"


async def test_a_change_to_tests_only_is_not_a_fix(tmp_path: Path) -> None:
    s = state("own_code", True, tests_only=True)
    got = await ship(s, "open_pr", tmp_path)
    assert (got.outcome, got.reason) == ("rca_only", "no_source_change")
    assert "did not edit any source file" in explain(s, got) and OUTSIDE not in explain(s, got)


@pytest.mark.parametrize(
    ("skip", "outcome", "reason"),
    [
        ("needs a human decision (D13)", "escalate", "needs_human"),
        ("flag-only mitigation: push_v2 rolled back (D13)", "rca_only", "flag_config"),
        ("cannot be reproduced automatically (D14)", "rca_only", "repro_failed"),
        ("no test tier allowed by agent type web-crash applies", "rca_only", "repro_failed"),
    ],
)
async def test_a_skipped_fix_plan_keeps_its_reason(
    tmp_path: Path, skip: str, outcome: str, reason: str
) -> None:
    s = state("own_code", None)
    s.fix_plan = FixPlan(skip=skip)
    got = await ship(s, "open_pr", tmp_path)
    assert (got.outcome, got.reason) == (outcome, reason)
    assert OUTSIDE not in explain(s, got)


async def test_a_flag_rollback_says_the_flag_is_the_defect(tmp_path: Path) -> None:
    s = state("flag_config", None)
    s.mitigation = Mitigation(flag="push_v2", action="rolled_back", detail="push_v2 100% -> 0%")
    got = await ship(s, "open_pr", tmp_path)
    assert (got.outcome, got.reason) == ("rca_only", "flag_config")
    assert "flag's configuration is the defect" in nodes.app_comment(s, None)
