# 0006. Local stand-ins for internal infrastructure, grouped in compose profiles

- Status: accepted · Date: 2026-10-04

## Context
Uber's pipeline uses internal systems (Healthline, Wisdom, Artifactory, device lab, Sourcegraph, internal incident tooling). The project must run on one 24 GB laptop and in CI.

## Decision
Open-source or self-built stand-ins, each labelled: Vitals ≈ Healthline, BugDrop ≈ Wisdom, MinIO ≈ Artifactory (Chainguard image — official MinIO images are no longer published), Playwright + Toxiproxy + CDP ≈ device lab, our code-search server ≈ Sourcegraph, a small incidents service, Jaeger/Loki/Prometheus/Unleash/Phoenix as themselves. Docker Compose profiles (`core`, `obs`, `flags`, `faults`, later `target`, `app`) keep memory in check.

## Consequences
Fully reproducible locally; mapping table maintained in `docs/ARCHITECTURE.md`.
