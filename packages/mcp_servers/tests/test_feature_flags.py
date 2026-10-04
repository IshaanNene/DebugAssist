from __future__ import annotations

import pytest

from debugassist.mcp_servers.feature_flags import two_proportion_z


def test_crash_rate_difference_is_significant() -> None:
    # The VIT-1001 numbers: 4/8 exposed sessions crashed vs 0/232 unexposed.
    z, p = two_proportion_z(4, 8, 0, 232)
    assert z == pytest.approx(10.86, abs=0.01) and p < 1e-20


def test_equal_rates_are_not_significant() -> None:
    z, p = two_proportion_z(5, 100, 5, 100)
    assert z == 0 and p == pytest.approx(1.0)


def test_empty_groups() -> None:
    assert two_proportion_z(0, 0, 3, 10) == (0.0, 1.0)
