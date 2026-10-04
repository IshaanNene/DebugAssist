# Progress

| Phase | Status | Date | Notes |
|---|---|---|---|
| P0 Plan & scaffold | ✅ done | 2026-10-04 | See below |
| P1 Decision engine | ⏭ next | | |

## P0 — Plan & scaffold (2026-10-04)

**Done**
- `docs/SPEC.md` (verbatim), `docs/PLAN.md` with review amendments A1–A10 (OpenRouter gpt-oss-120b instead of Claude; LangChain `create_agent` harness; LLMDecider baseline via system-one-adapter).
- uv workspace (Python 3.13) with `debugassist-core` and `debugassist-decisions` packages under the shared `debugassist.*` namespace.
- `debugassist.core.settings`: per-integration run modes (`live`/`mock`/`replay`) resolved from credentials or `DA_MODE_*`.
- Tooling: ruff, pyright strict, pytest (+asyncio), pre-commit (incl. a hook that refuses `.env`), GitHub Actions CI (mock mode, no secrets).
- `infra/docker-compose.yml` with profiles `core` (Postgres 17, Redis 8, MinIO), `obs` (Jaeger 2.21, Loki 3.7, Prometheus 3.15, Phoenix 20.19), `flags` (Unleash 8.2), `faults` (Toxiproxy 2.12). All healthy locally, ~0.85 GB RAM.
- Live verification: Clef and Clef-flash on Workers AI return 200 inside Cloudflare's `{"result": …}` envelope; fixtures in `packages/decisions/tests/fixtures/workers_ai/`.
- Cloudflare Claude Code plugin installed (`cloudflare@cloudflare`).
- `CLAUDE.md`, ADRs 0001–0006.

**Verify**
```
make bootstrap && make check
make up && make ps
make clef-smoke
```

**Open items**
- Jira Cloud live mode also needs `JIRA_BASE_URL` and `JIRA_EMAIL`.
- Slack: mock inbox (no workspace given).
- GitHub token for the demo repos (`GITHUB_TOKEN`, fine-grained PAT) needed by P2a/P3; `gh` CLI auth is used to create the repos.
