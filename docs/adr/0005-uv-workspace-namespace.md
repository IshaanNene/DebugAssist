# 0005. uv workspace with a shared `debugassist.*` namespace, Python 3.13

- Status: accepted · Date: 2026-10-04

## Context
Mirrors Uber's Python monorepo: many packages owned separately, one build, packaged per agent type (PEX).

## Decision
One uv workspace; each package under `packages/<name>` contributes to the implicit namespace package `debugassist` (`debugassist.core`, `debugassist.decisions`, …). Python pinned to 3.13 for wheel coverage.

## Consequences
Clean imports across packages; each package keeps its own dependency list, which PEX builds per agent type can subset.
