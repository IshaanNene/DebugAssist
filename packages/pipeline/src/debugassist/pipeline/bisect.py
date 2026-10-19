"""Prove the culprit commit by running the reproduction test (DA_BISECT=1), no model.

Once a fix is validated, its reproduction test is known to fail on the release for the reported reason. This puts
that test on older commits: first the earlier release tags, newest first, until one where it passes (the last good
release); then `git bisect` between that release and the shipped one. Each commit is judged like the
reproduction itself: the test reproduces the bug → bad; it passes → good; it fails for another reason (e.g. code it
calls did not exist yet) → skip. The result is a commit range a reviewer can re-run, set beside the RCA's own claim.

The worktree is left as found: its changes since HEAD (tracked edits and files marked intent-to-add, as the
sandbox's diff marks new files) are saved as a patch, the tree is reset for the bisect, and afterwards HEAD and the
patch are restored. Other untracked files (installed dependencies, caches) are never deleted — only the test file
this places is removed again. Bisect refs are per worktree, so the main checkout is not touched.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, cast

from debugassist.core.workspace import Workspace

Verdict = Literal["good", "bad", "skip"]
MAX_TAGS = 10  # earlier releases tried for a last good one, at doubling distances
MAX_STEPS = 40


def _git(
    wt: Path, *args: str, stdin: str | None = None, check: bool = False
) -> subprocess.CompletedProcess[str]:
    return Workspace(wt).git(*args, input=stdin, check=check)


def _sha(wt: Path, ref: str) -> str:
    return _git(wt, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}").stdout.strip()


def earlier_tags(wt: Path, base: str, limit: int = MAX_TAGS) -> list[str]:
    """Release tags that are ancestors of `base` (excluding tags on `base`'s own commit), to try newest first at
    doubling distances — the 1st, 2nd, 4th, 8th … and the oldest — so an old last-good release is reached in a few
    runs; bisect then narrows the range."""
    head = _sha(wt, base)
    tags = [
        t
        for t in _git(wt, "tag", "--merged", base, "--sort=-creatordate").stdout.split()
        if _sha(wt, t) != head
    ]
    picks: list[int] = []
    i = 1
    while i - 1 < len(tags):
        picks.append(i - 1)
        i *= 2
    if tags and len(tags) - 1 not in picks:
        picks.append(len(tags) - 1)
    return [tags[k] for k in picks[:limit]]


_EXC = re.compile(r"\b([A-Z][A-Za-z0-9_]*(?:Error|Exception))\b")


def exceptions(output: str) -> set[str]:
    """Exception class names in a test run's output (the failure's kind, e.g. {"AttributeError"})."""
    return set(_EXC.findall(output))


def prove(
    wt: Path,
    base: str,
    test_file: str,
    command: str,
    unrelated: Callable[[int, str], bool],
    run: Callable[[str], tuple[int, str]],
    *,
    log: Callable[[str], None] = lambda _: None,
) -> dict[str, Any]:
    """Bisect `base`'s history with the reproduction test at `test_file` (as it is in the worktree now).

    run(command) runs the test in the worktree's environment; unrelated(exit_code, output) says a failing run
    failed for a reason other than a bug (syntax, missing test files, a time-out). A commit is bad only when the
    test fails with an exception it also raises on the release: an older commit where it fails otherwise (an
    ImportError because the code it calls did not exist yet) is skipped, not blamed. Returns
    {result: found | narrowed | no_good_release | unbisectable, ...} — `found` with good, first_bad, subject,
    steps, skipped; `narrowed` with the candidates when commits where the test cannot run sit next to the change."""
    ws = Workspace(wt)
    test_src = ws.read(test_file)
    head_ref = _git(wt, "symbolic-ref", "-q", "HEAD").stdout.strip()
    head_sha = _sha(wt, "HEAD")
    saved = _git(
        wt, "diff", "--binary", head_sha
    ).stdout  # the fix and its tests (new files are intent-to-add)
    if test_file not in _git(wt, "diff", "--name-only", head_sha).stdout.split():
        _git(wt, "add", "--intent-to-add", "--", test_file)  # keep the test in the saved patch too
        saved = _git(wt, "diff", "--binary", head_sha).stdout
    tried: list[dict[str, str]] = []
    out: dict[str, Any] = {"test_file": test_file, "command": command, "base": base}

    def clean() -> None:
        """Tracked files back to the commit; the placed test removed. Nothing else untracked is touched."""
        _git(wt, "reset", "-q", "--hard")
        if not _git(wt, "ls-files", "--", test_file).stdout.strip():
            ws.remove(test_file)

    want: set[str] = set()  # the release failure's exceptions, set by the first probe

    def classify(code: int, output: str) -> Verdict:
        if code == 0:
            return "good"
        if unrelated(code, output):
            return "skip"
        return "bad" if not want or want & exceptions(output) else "skip"

    def probe(first: bool = False) -> Verdict:
        """The test on the commit checked out now; the tree is clean again afterwards."""
        ws.write(test_file, test_src)
        try:
            code, output = run(command)
            if first and code:
                want.update(exceptions(output))
                out["failing_cases"] = failing_cases(output)
            return classify(code, output)
        finally:
            clean()

    def at(ref: str, first: bool = False) -> Verdict:
        clean()
        _git(wt, "checkout", "-q", "--detach", ref, check=True)
        return probe(first)

    try:
        clean()
        if at(base, first=True) != "bad":
            return {**out, "result": "unbisectable", "why": f"the test does not reproduce the bug at {base}"}
        good = None
        for tag in earlier_tags(wt, base):
            v = at(tag)
            tried.append({"tag": tag, "verdict": v})
            log(f"  {tag}: {v}")
            if v == "good":
                good = tag
                break
        out["tags_tried"] = tried
        if good is None:
            seen_bad = any(t["verdict"] == "bad" for t in tried)
            return {
                **out,
                "result": "no_good_release" if seen_bad else "unbisectable",
                "why": "the test fails on every earlier release tried in this history (a regression from a release "
                "on another branch, or a bug older than the releases tried)"
                if seen_bad
                else "the test does not run on any earlier release tried",
            }
        clean()
        _git(wt, "bisect", "start", base, good, check=True)
        steps, skipped = 0, list[str]()
        first_bad = None
        while steps < MAX_STEPS:
            steps += 1
            current = _sha(wt, "HEAD")
            v = probe()
            if v == "skip":
                skipped.append(current[:10])
            res = _git(wt, "bisect", v)
            text = res.stdout + res.stderr
            if m := re.search(r"^([0-9a-f]{40}) is the first '?bad'? commit", text, re.M):
                first_bad = m.group(1)
                break
            if "only skipped commits left" in text or res.returncode not in (0,):
                cands = re.findall(r"^([0-9a-f]{40})$", text, re.M)
                out.update(candidates=[c[:10] for c in cands])
                break
        _git(wt, "bisect", "reset")
        out.update(
            good=good,
            good_sha=_sha(wt, good)[:10],
            steps=steps,
            skipped=skipped,
            release_failure=sorted(want),
        )
        if first_bad is None:
            if out.get("candidates"):  # commits where the test cannot run sit next to the change
                return {**out, "result": "narrowed", "why": "the first bad commit is one of the candidates"}
            return {**out, "result": "unbisectable", "why": "bisect did not converge"}
        subject = _git(wt, "log", "-1", "--format=%s", first_bad).stdout.strip()
        return {**out, "result": "found", "first_bad": first_bad[:10], "subject": subject}
    finally:
        _git(wt, "bisect", "reset")  # (no -q: `bisect reset` takes a commit, and would reject it)
        clean()
        _git(wt, "checkout", "-q", "-f", head_ref.removeprefix("refs/heads/") if head_ref else head_sha)
        _git(wt, "reset", "-q", "--hard", head_sha)
        if saved:
            _git(wt, "apply", "--binary", "-", stdin=saved)


_FAILED = re.compile(r"^FAILED (\S+?)(?: - .*)?$", re.M)  # pytest: FAILED tests/test_x.py::test_y - …
_VITEST = re.compile(
    r"^\s*FAIL\s+\S+\.(?:test|spec)\.[cm]?[jt]sx?\s+>\s+(.+?)\s*$", re.M
)  # FAIL file > suite > case
_GO = re.compile(r"^\s*--- FAIL: (\S+)", re.M)  # --- FAIL: TestHead (0.00s)


def failing_cases(output: str) -> list[str]:
    """The test cases a run reports as failed: pytest node ids, vitest `suite > case` names, Go test names."""
    found = _FAILED.findall(output) + _VITEST.findall(output) + _GO.findall(output)
    return list(dict.fromkeys(found))


def case_command(command: str, test_file: str) -> Callable[[str], str] | None:
    """The command for one failing case of `test_file`, for the runners whose output `failing_cases` reads
    (ROADMAP-100 086); None when the command is none of them (bisect then works on the whole file only)."""
    if test_file not in command:
        return None
    if "pytest" in command:
        return lambda case: command.replace(test_file, shlex.quote(case))
    if "vitest" in command:
        # -t matches the full name ("suite case"); the last `>` segment is the case and is enough to select it.
        return lambda case: f"{command} -t {shlex.quote(re.escape(case.split(' > ')[-1]))}"
    if re.search(r"\bgo test\b", command):
        return lambda case: f"{command} -run {shlex.quote('^' + re.escape(case.split('/')[0]) + '$')}"
    return None


pytest_case_command = case_command  # the name callers used before vitest and Go were supported


def prove_by_case(
    wt: Path,
    base: str,
    test_file: str,
    command: str,
    case_command: Callable[[str], str] | None,
    unrelated: Callable[[int, str], bool],
    run: Callable[[str], tuple[int, str]],
    *,
    max_cases: int = 4,
    log: Callable[[str], None] = lambda _: None,
) -> dict[str, Any]:
    """`prove` on the whole test file; if no earlier release passes it, on each of its failing cases alone.

    An agent's reproduction usually asserts more than the behaviour that regressed (it encodes the fix's
    requirements too), so the file fails on every release; a case that asserts only the old behaviour passes on
    the last good release and bisects. case_command(case) is the command for one case (None: whole file only)."""
    whole = prove(wt, base, test_file, command, unrelated, run, log=log)
    cases = cast(list[str], whole.get("failing_cases") or [])
    if whole.get("result") == "found" or case_command is None or len(cases) < 2:
        return whole
    by_case: list[dict[str, Any]] = []
    for case in cases[:max_cases]:
        r = prove(wt, base, test_file, case_command(case), unrelated, run, log=log)
        by_case.append(
            {"case": case, **{k: r.get(k) for k in ("result", "good", "first_bad", "subject", "steps")}}
        )
        if r.get("result") == "found":
            return {**r, "case": case, "whole_file": whole.get("result"), "by_case": by_case}
    return {**whole, "by_case": by_case}


def agrees(found: dict[str, Any], suspect: str | None) -> bool | None:
    """Whether the bisected commit is the one the RCA named (None when either is missing)."""
    if found.get("result") != "found" or not suspect:
        return None
    a, b = str(found["first_bad"]).lower(), suspect.strip().lower()
    return a.startswith(b[:7]) or b.startswith(a[:7])
