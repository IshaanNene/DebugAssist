"""Interval estimates for the report: rates from tens of runs are shown with their uncertainty."""

from __future__ import annotations

from math import sqrt


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """The Wilson score interval for k successes in n trials (95% by default); (0, 1) when n is 0.

    Unlike the normal approximation it stays inside [0, 1] and behaves at k = 0 or k = n, which small eval arms hit.
    """
    if n == 0:
        return 0.0, 1.0
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def rate_with_interval(k: int, n: int) -> str:
    """'0.65 [0.54–0.75] (49/75)'."""
    if n == 0:
        return "–"
    lo, hi = wilson(k, n)
    return f"{k / n:.2f} [{lo:.2f}–{hi:.2f}] ({k}/{n})"
