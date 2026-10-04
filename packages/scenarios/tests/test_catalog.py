import re

import pytest

from debugassist.scenarios.catalog import GROUNDTRUTH, Bug, get_bug, load_catalog
from debugassist.simulator.scenarios import SCENARIOS

BUGS = list(load_catalog().values())
D05_CATEGORIES = {"own_code", "third_party_lib", "infra", "network", "flag_config", "device_os", "not_a_bug"}


def test_catalog_has_the_three_demos_plus_five() -> None:
    ids = [b.id for b in BUGS]
    assert ids[:3] == ["BUG-001", "BUG-002", "BUG-003"] and len(ids) >= 8
    assert {b.language for b in BUGS} >= {"typescript", "python", "go"}
    assert any(b.expected_outcome != "pr" for b in BUGS)  # at least one "not our bug"


@pytest.mark.parametrize("bug", BUGS, ids=lambda b: b.id)
def test_referenced_files_exist(bug: Bug) -> None:
    for patches in bug.injection.repos.values():
        for rel in patches:
            assert bug.path(rel).is_file(), rel
    if bug.ground_truth.fix:
        assert bug.path(bug.ground_truth.fix).is_file()
    for h in bug.ground_truth.hidden_tests:
        assert bug.path(h.src).is_file()
    assert bug.trigger.scenario in SCENARIOS
    assert bug.category in D05_CATEGORIES
    if bug.injection.repos:
        assert bug.injection.release and re.fullmatch(r"\d+\.\d+\.\d+", bug.injection.release)
        assert bug.ground_truth.location.file and bug.ground_truth.location.function


LEAKS = re.compile(r"BUG-\d{3}|groundtruth|ground truth|inject|catalog|DebugAssist", re.I)


@pytest.mark.parametrize("bug", [b for b in BUGS if b.injection.repos], ids=lambda b: b.id)
def test_regression_commits_do_not_leak_ground_truth(bug: Bug) -> None:
    for patches in bug.injection.repos.values():
        for rel in patches:
            text = bug.path(rel).read_text()
            leak = LEAKS.search(text)
            assert leak is None, f"{rel} mentions {leak.group(0)!r}"
            assert re.search(r"^From: .+ <.+@miniride\.dev>$", text, re.M), (
                "commit author should be a MiniRide engineer"
            )


def test_versions_are_unique_per_scenario() -> None:
    releases = [b.injection.release for b in BUGS if b.injection.release]
    assert len(releases) == len(set(releases))


def test_short_ids() -> None:
    assert get_bug("2").id == "BUG-002" and get_bug("BUG-008").id == "BUG-008"
    with pytest.raises(KeyError):
        get_bug("999")


def test_groundtruth_readme_warns_about_isolation() -> None:
    assert "never" in (GROUNDTRUTH / "README.md").read_text().lower()
