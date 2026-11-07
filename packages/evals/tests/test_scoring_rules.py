"""Row-level scoring rules: validated fixes on not-our-bug cases, and discovery times from a clock that ran ahead."""

from __future__ import annotations

from debugassist.evals import score
from debugassist.scenarios.catalog import get_bug


def test_a_negative_discovery_time_is_dropped_and_the_skew_kept() -> None:
    assert score.discovery_times(120.0, 400.0) == {
        "discovery_to_rca_s": 120.0,
        "discovery_to_end_s": 400.0,
        "discovery_clock_skew_s": None,
    }
    # 20261010-132740-bd-1001: the RCA "before" the report, the end after it; neither is a measurement
    assert score.discovery_times(-131.1, 58.5) == {
        "discovery_to_rca_s": None,
        "discovery_to_end_s": None,
        "discovery_clock_skew_s": 131.1,
    }
    assert score.discovery_times(None, None)["discovery_clock_skew_s"] is None


def test_a_validated_fix_counts_only_where_a_fix_is_expected() -> None:
    not_ours, ours = get_bug("BUG-006"), get_bug("BUG-001")
    assert not_ours.expected_outcome != "pr" and ours.expected_outcome == "pr"
    row = {"validated": True, "discovery_to_rca_s": -638.3, "discovery_to_end_s": -358.4}
    assert not score.fix_success(score.normalize(row, not_ours))
    fixed = score.normalize(row, ours)
    assert score.fix_success(fixed) and fixed["discovery_to_rca_s"] is None
    assert score.normalize(fixed, ours) == fixed  # idempotent: rescoring twice changes nothing
    assert score.fix_success({"validated": True})  # rows from before the field: as they were
