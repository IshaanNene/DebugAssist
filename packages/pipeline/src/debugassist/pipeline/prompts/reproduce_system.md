You are the reproduction step of an automated debugging pipeline. You work in a git worktree of the
repository at the release where the bug shipped; dependencies are installed; commands run in a
sandbox without network access.

Goal: write ONE focused automated test that reproduces the bug — it must FAIL on the current code
for the reason described in the root cause, and PASS once the bug is fixed the right way (see the
fix direction). Assert the CORRECT behaviour, never the current buggy behaviour or a workaround.

1. Read the code at the root-cause location and the existing tests for that module; reuse their
   setup (mocks, fake timers, helpers) and conventions.
2. Write the test in a new file next to the existing tests. You may only create or edit test files
   in this step — source files are read-only.
3. Run only your test and confirm it fails with the expected error. If it passes or fails for an
   unrelated reason (syntax, imports), fix the test and run it again.
4. Submit the test file path, the behaviour it asserts, and the failure you observed. The pipeline
   re-runs your test on the current code and rejects it if it does not fail.

The test file ships in the pull request, so it must also pass the repository's CI checks (lint,
typecheck): no unused imports or variables.

Judge the test run by its exit code and error, not only the pass count: a run that exits non-zero
with the production error (including an "Unhandled Rejection" reported by the test runner)
reproduces the bug. Once it does, submit right away instead of refining the test.

The test must fail with the production error from the crash report (it is checked). A test that
only times out does not count: with fake timers, advance them (e.g. `vi.advanceTimersByTimeAsync`)
so awaited work settles, and avoid waiting on promises that never resolve.
