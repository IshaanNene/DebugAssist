"""Regression test for issue #484: next_version with old-style prereleases.

Adapted from python-semver's tests/test_issue484.py at 8c0a3f7 (BSD-3-Clause). The issue states that "0.1.2-rc3"
should become "0.1.2-rc4" *or* "0.1.2-rc.4", so the three old-style cases accept either form; the two tests that
guard existing behaviour are upstream's, verbatim.
"""

from semver import Version


def test_issue_484_rc3_to_rc4():
    """Old-style prerelease 'rc3' should bump to 'rc4' (or 'rc.4'), not reset to 'rc.1'."""
    v = Version.parse("0.1.2-rc3")
    assert str(v.next_version("prerelease")) in ("0.1.2-rc4", "0.1.2-rc.4")


def test_issue_484_rc9_to_rc10():
    """Ensure numeric bumping works across digit boundaries."""
    v = Version.parse("1.2.3-rc9")
    assert str(v.next_version("prerelease")) in ("1.2.3-rc10", "1.2.3-rc.10")


def test_issue_484_dot_style_unchanged():
    """Dot-separated prereleases should still work as before."""
    v = Version.parse("0.1.2-rc.3")
    assert str(v.next_version("prerelease")) == "0.1.2-rc.4"


def test_issue_484_different_token():
    """A different prerelease token should still reset to rc.1."""
    v = Version.parse("1.2.3-alpha1")
    assert str(v.next_version("prerelease")) == "1.2.3-rc.1"


def test_issue_484_custom_token():
    """Custom prerelease token should be respected."""
    v = Version.parse("1.2.3-beta2")
    assert str(v.next_version("prerelease", "beta")) in ("1.2.3-beta3", "1.2.3-beta.3")
