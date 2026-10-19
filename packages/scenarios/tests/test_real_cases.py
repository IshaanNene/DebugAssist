"""Every real open-source case (groundtruth/real/, sources/github/issues/) is complete and self-consistent — the
mechanical half of the ROADMAP's checklist for adding one. The other half (the hidden test fails on the buggy
commit and passes with the upstream fix; the fix unreachable from the checkout) is verified when a case is added
and recorded in its `validation`; `scenarios.real.prepare` re-checks reachability whenever it builds a checkout."""

from __future__ import annotations

import re

import pytest
import yaml

from debugassist.integrations.sandbox import IMAGES
from debugassist.scenarios import real

CASES = real.cases()
SHA = re.compile(r"^[0-9a-f]{40}$")


def test_there_are_cases_in_more_than_one_language() -> None:
    langs = {real.load_case(c).language for c in CASES}
    assert len(CASES) >= 9 and {"python", "go", "typescript"} <= langs


@pytest.mark.parametrize("cid", CASES)
def test_case_and_input_agree(cid: str) -> None:
    case = real.load_case(cid)
    issue = real.load_issue(case.source)
    assert issue.case == case.id and issue.repo == case.repo and issue.language == case.language
    assert case.language in IMAGES  # the sandbox has an image for it
    assert issue.url == case.upstream["issue"]
    for k in ("fix_commit", "buggy_commit"):
        assert SHA.match(case.upstream[k]), k
    assert issue.checkout.commit == case.upstream["buggy_commit"]  # the report is run on the fix's parent
    assert case.upstream.get("pr_head") is None or SHA.match(case.upstream["pr_head"])


@pytest.mark.parametrize("cid", CASES)
def test_hidden_tests_exist_and_say_how_to_run(cid: str) -> None:
    case = real.load_case(cid)
    assert case.ground_truth.hidden_tests and case.ground_truth.rca_facts
    for h in case.ground_truth.hidden_tests:
        assert case.path(h.src).is_file(), h.src
        assert h.repo == case.repo and h.command, h.src
    assert case.validation.get("verified")  # how it was verified: `how`, or a comment in the older cases


@pytest.mark.parametrize("cid", CASES)
def test_the_checkout_config_says_how_to_build_and_test(cid: str) -> None:
    issue = real.load_issue(real.load_case(cid).source)
    cfg = yaml.safe_load(issue.checkout.config)
    comp = cfg["components"][issue.component]
    assert comp["language"] == issue.language
    for k in ("setup", "test", "test_one"):
        assert comp.get(k), k


@pytest.mark.parametrize("cid", CASES)
def test_the_answer_is_not_in_the_report(cid: str) -> None:
    case = real.load_case(cid)
    issue = real.load_issue(case.source)
    # `withheld` lists what was cut from the report; absent when nothing was (python-semver#484)
    loc = case.ground_truth.location
    assert loc.file not in issue.body, "the report names the file upstream changed"
    for sha in (case.upstream["fix_commit"], case.upstream.get("pr_head") or ""):
        assert not sha or sha[:7] not in issue.body
