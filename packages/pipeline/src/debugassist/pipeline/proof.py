"""When a test run counts as a reproduction of the reported bug (ROADMAP-100 031, 022).

The rules that decide whether the pipeline may claim "fails on the release with the production error": they gate
every reproduction, the fix contract and the release checks, so they live in one small module with their own tests
and a mutation score (`make mutate`).
"""

from __future__ import annotations

import re

from debugassist.pipeline.state import Issue

# How test runners report a failed assertion: pytest / unittest, vitest / jest / chai, node:assert, Go's testing.
ASSERTION_FAILED = re.compile(
    r"AssertionError|^E\s+assert\b|\bassert .* (==|!=|is|in) |Expected:|Received:|expected .+ to |"
    r"AssertionError \[ERR_ASSERTION\]|^\s+\S+_test\.go:\d+: |--- FAIL: ",
    re.M,
)
TIMEOUT_MARKERS = ("Test timed out", "Exceeded timeout of", "Timeout of", "Failed: Timeout >")


def error_signature(issue: Issue) -> str | None:
    """The production error message a reproduction must show (crashes only), e.g.
    "Cannot read properties of undefined (reading 'riderId')" from "TypeError: Cannot read …"."""
    if issue.kind != "crash":
        return None
    msg = re.sub(r"^[A-Za-z_.]*(Error|Exception)\b:?\s*", "", issue.title).strip()
    return msg or None


REPORTED_ERROR = re.compile(
    r"\w*(Error|Exception)\b|Traceback|panic:|crash|\bthrow(s|n|ing)?\b|\brais(e|es|ed|ing)\b", re.I
)


def wrong_value_report(issue: Issue) -> bool:
    """A report of a wrong result rather than an error: not a crash, and neither its title nor its text names an
    exception (a GitHub issue that pastes a traceback is a crash report whatever its kind)."""
    if issue.kind == "crash":
        return False
    report = issue.report or {}
    text = " ".join([issue.title, *(str(v) for v in report.values() if isinstance(v, str))])
    return not REPORTED_ERROR.search(text)


def error_type(issue: Issue) -> str | None:
    """The reported exception's class name ("TypeError", "KeyError"), last component only."""
    m = re.match(r"^([A-Za-z_][\w.]*(?:Error|Exception))\b", issue.title)
    return m.group(1).split(".")[-1] if m and issue.kind == "crash" else None


def error_pattern(issue: Issue) -> re.Pattern[str] | None:
    """What the reproduction's output must contain to show the reported error (ROADMAP-100 011).

    Not the message as a substring: numbers and addresses vary between runs (`index 7`, `0x7f3a…`), whitespace
    between runtimes, and a test that only *asserts* the message text ("expected … to throw 'Cannot read …'")
    contains it without raising it. So: the exception type immediately before the message, as a runtime prints a
    raised error, with numbers and hex addresses free and runs of whitespace equal."""
    sig = error_signature(issue)
    if not sig:
        return None
    parts = re.split(r"(0x[0-9a-fA-F]+|\d+(?:\.\d+)?)", sig)
    body = "".join(
        r"\S+" if i % 2 else re.sub(r"(\\\s)+", r"\\s+", re.escape(p)) for i, p in enumerate(parts)
    )
    kind = error_type(issue)
    return re.compile((rf"(?<!\w){re.escape(kind)}:\s*" if kind else "") + body)


def repro_problem(cmd: str, exit_code: int, output: str, issue: Issue) -> str | None:
    """Why a test run on the buggy release does not count as a reproduction (None = it does).

    A test that only times out fails with or without a fix (e.g. fake timers never advanced), and one
    that fails with some other error does not show the reported bug; both used to be accepted and then
    frozen, leaving the fix step an impossible target.
    """
    if exit_code == 0:
        return f"`{cmd}` passes on the current (buggy) code, so it does not reproduce the bug."
    if "No test files found" in output or "SyntaxError" in output or "Cannot find module" in output:
        return f"`{cmd}` failed for an unrelated reason:\n{output[-800:]}"
    if any(m in output for m in TIMEOUT_MARKERS):
        return (
            f"`{cmd}` fails only by timing out, which happens with or without a fix (fake timers never "
            f"advanced? an awaited promise that never settles?). Make it fail with the production error.\n{output[-600:]}"
        )
    if wrong_value_report(issue) and not ASSERTION_FAILED.search(output):
        # A wrong value, not a crash (ROADMAP-100 012): the test must fail on an assertion about the value, not on an
        # error of its own (a NameError, a bad import, a typo) that would fail with or without the bug.
        return (
            f"`{cmd}` fails, but not on an assertion: the report is a wrong result, so the test must assert the "
            f"correct value and fail on that assertion.\n{output[-600:]}"
        )
    pattern = error_pattern(issue)
    if pattern is not None and not pattern.search(output):
        kind, sig = error_type(issue), error_signature(issue)
        shown = f"{kind}: {sig}" if kind else sig
        return (
            f"`{cmd}` fails, but not with the reported error `{shown}` raised by the code under test (a test "
            f"that only asserts the message does not count); reproduce that failure.\n{output[-600:]}"
        )
    return None
