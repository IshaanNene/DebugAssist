---
name: web-client-fixes
description: How to fix a defect in a TypeScript/React web client so reviewers accept it — scope, tests, conventions. Loaded by the fix step of the web-crash agent type.
---

# Fixing a web-client defect

- Fix the root cause named by the RCA, not the symptom. If the fix needs a second change to work in the
  user's real conditions (slow network, backgrounded tab, flag variant), make both and say why.
- Keep the diff small and local: no drive-by refactors, renames or formatting changes outside the lines
  you need. Reviewers merge small diffs.
- Follow the code around you: naming, error handling, how modules are mocked in existing tests.
- Keep behaviour behind feature flags as it is unless the RCA says the flag itself is the problem.
- The reproduction test ships with the fix: name it after the behaviour it protects, and keep it
  deterministic (fake timers advanced explicitly; no real sleeps or network).
- Run the repository's own checks (tests, lint, typecheck) before you submit.

## Lessons from reviews

Corrections from code review, added through the feedback loop (D18) after a human approves the change.
