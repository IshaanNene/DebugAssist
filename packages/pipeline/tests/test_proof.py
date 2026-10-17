"""The reproduction rules (`pipeline/proof.py`), case by case. These are the tests the mutation score is measured
with (`make mutate`): each rule has a case that passes and one that must be rejected."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from debugassist.pipeline import proof
from debugassist.pipeline.state import Issue, RunState

FIXTURE = Path(__file__).parent / "fixtures" / "run_state.json"
CMD = "pytest -q tests/test_x.py"


def issue(kind: str = "crash", title: str = "TypeError: Cannot read properties of undefined (reading 'riderId')",
          body: str = "") -> Issue:  # fmt: skip
    s = RunState.model_validate(json.loads(FIXTURE.read_text()))
    assert s.issue
    s.issue.kind, s.issue.title, s.issue.report = kind, title, {"body": body}
    return s.issue


RAISED = "Uncaught TypeError: Cannot read properties of undefined (reading 'riderId')\n  at route"


def test_a_passing_test_reproduces_nothing() -> None:
    assert (proof.repro_problem(CMD, 0, RAISED, issue()) or "").startswith(
        f"`{CMD}` passes on the current (buggy) code"
    )


@pytest.mark.parametrize("marker", ["No test files found", "SyntaxError: x", "Cannot find module 'y'"])
def test_unrelated_failures_are_rejected(marker: str) -> None:
    assert "unrelated reason" in (proof.repro_problem(CMD, 1, f"{marker}\n{RAISED}", issue()) or "")


@pytest.mark.parametrize("marker", proof.TIMEOUT_MARKERS)
def test_a_timeout_is_no_reproduction(marker: str) -> None:
    assert "timing out" in (proof.repro_problem(CMD, 1, f"{marker} 5000ms\n{RAISED}", issue()) or "")


def test_the_reported_crash_reproduces() -> None:
    assert proof.repro_problem(CMD, 1, RAISED, issue()) is None


def test_another_error_does_not_reproduce_the_crash() -> None:
    problem = proof.repro_problem(CMD, 1, "Uncaught TypeError: x is not a function", issue())
    assert problem is not None and "TypeError: Cannot read properties" in problem


def test_an_assertion_that_quotes_the_message_is_not_the_crash() -> None:
    out = "AssertionError: expected [Function] to throw 'Cannot read properties of undefined (reading 'riderId')'"
    assert proof.repro_problem(CMD, 1, out, issue()) is not None


def test_numbers_and_whitespace_may_vary() -> None:
    i = issue(title="IndexError: list index out of range at 3")
    assert proof.repro_problem(CMD, 1, "E   IndexError: list  index out of range at 7", i) is None
    assert proof.repro_problem(CMD, 1, "E   IndexError: list index out of range at 0x7f", i) is None
    assert proof.repro_problem(CMD, 1, "E   IndexError: tuple index out of range at 7", i) is not None


def test_signature_type_and_pattern_parts() -> None:
    i = issue(title="requests.exceptions.HTTPError: 503 Server Error")
    assert proof.error_signature(i) == "503 Server Error" and proof.error_type(i) == "HTTPError"
    pattern = proof.error_pattern(i)
    assert pattern is not None and pattern.search("requests.exceptions.HTTPError: 502 Server Error")
    assert not pattern.search("MyHTTPError: 502 Server Error")
    assert (
        proof.error_signature(issue(kind="bug_report")) is None
        and proof.error_type(issue(kind="report")) is None
    )
    assert proof.error_pattern(issue(kind="bug_report")) is None
    assert proof.error_signature(issue(title="TypeError:")) is None


def test_a_wrong_value_report_needs_an_assertion() -> None:
    i = issue(kind="bug_report", title="Fare shows $0 for airport trips", body="Expected about $40.")
    assert proof.wrong_value_report(i)
    assert proof.repro_problem(CMD, 1, "E       assert 0 == 40", i) is None
    assert proof.repro_problem(CMD, 1, "--- FAIL: TestFare (0.00s)", i) is None
    problem = proof.repro_problem(CMD, 1, "NameError: name 'fare' is not defined", i)
    assert problem is not None and "not on an assertion" in problem


@pytest.mark.parametrize(
    ("kind", "title", "body", "wrong_value"),
    [
        ("crash", "Fare shows $0", "", False),
        ("bug_report", "head(xs, 0) raises", "", False),
        ("bug_report", "Fare shows $0", "Traceback (most recent call last)", False),
        ("bug_report", "Fare shows $0", "a panic: in the logs", False),
        ("bug_report", "Fare shows $0", "Expected about $40", True),
    ],
)
def test_which_reports_are_wrong_value_reports(kind: str, title: str, body: str, wrong_value: bool) -> None:
    assert proof.wrong_value_report(issue(kind=kind, title=title, body=body)) is wrong_value


@pytest.mark.parametrize(
    "line",
    ["AssertionError", "E   assert 1 == 2", "assert x == y failed", "Expected: 40", "Received: 0",
     "expected 0 to equal 40", "AssertionError [ERR_ASSERTION]: x", "    fare_test.go:12: got 0", "--- FAIL: TestX"],
)  # fmt: skip
def test_assertion_markers(line: str) -> None:
    assert proof.ASSERTION_FAILED.search(line)


@pytest.mark.parametrize(
    "line", ["NameError: name 'x'", "ImportError: no module", "SyntaxError: bad", "exit 1"]
)
def test_not_assertion_markers(line: str) -> None:
    assert not proof.ASSERTION_FAILED.search(line)


def test_the_report_title_and_body_are_read_as_separate_words() -> None:
    """Joined without a space, "…rais" + "e of fare" would read as "raise" and hide a wrong-value report."""
    assert proof.wrong_value_report(issue(kind="bug_report", title="Wrong rais", body="e of fare"))


@pytest.mark.parametrize(
    ("exit_code", "output", "keep"),
    [
        (1, "No test files found " + "x" * 900, 800),  # unrelated failure
        (1, "Test timed out " + "x" * 900, 600),  # timeout
        (1, "Uncaught TypeError: other " + "x" * 900, 600),  # the wrong error
    ],
)
def test_messages_name_the_command_and_keep_the_output_tail(exit_code: int, output: str, keep: int) -> None:
    problem = proof.repro_problem(CMD, exit_code, output, issue())
    assert problem is not None and problem.startswith(f"`{CMD}` ")
    assert problem.endswith(output[-keep:]) and not problem.endswith(output[-keep - 1 :])


def test_the_wrong_value_message_names_the_command_and_keeps_the_tail() -> None:
    i = issue(kind="bug_report", title="Fare shows $0", body="Expected about $40.")
    out = "NameError: name 'fare' is not defined " + "x" * 900
    problem = proof.repro_problem(CMD, 1, out, i)
    assert problem is not None and problem.startswith(f"`{CMD}` fails, but not on an assertion")
    assert problem.endswith(out[-600:]) and not problem.endswith(out[-601:])


def test_the_wrong_error_message_quotes_the_reported_error() -> None:
    problem = proof.repro_problem(CMD, 1, "TypeError: other", issue())
    assert problem is not None and problem.startswith(
        f"`{CMD}` fails, but not with the reported error `TypeError: "
    )
    assert "raised by the code under test" in problem
