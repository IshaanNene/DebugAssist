# Progress

| Phase | Status | Date | Notes |
|---|---|---|---|
| P0 Plan & scaffold | ✅ done | 2026-10-04 | See below |
| P1 Decision engine | ✅ done | 2026-10-04 | See below |
| P2a Target system + telemetry | ⏭ next | | |

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

## P1 — Decision engine (2026-10-04)

**Done**
- `debugassist.decisions.schema`: Pydantic request/response models enforcing every documented limit (1–64 questions, id regex, 2–255 options, 2–10 levels, required instructions, ≤4 images of PNG/JPEG/WebP data URLs, 13 MiB body); envelope unwrap; response-vs-request consistency checks.
- `images`: auto-resize/re-encode to ≤16 MP and ≤4 MiB each, ≤8 MiB total.
- Backends: `WorkersAIClef` (retries on 429/5xx/timeouts with backoff+jitter, no retry on 4xx), `LLMDecider` (gpt-oss-120b via `system-one-adapter`, OpenRouter host pinning), `LocalClef` (optional, HF `joint_schema_model.py`), `MockDecider` (deterministic, overridable). Circuit breaker + `FallbackBackend`.
- 18 versioned templates (D01–D18) with `$param` options, `foreach` per-item questions, two-stage high cardinality (D12); policy bands; LLM second opinion on escalation.
- `CompactState` token budgeting; `DecisionEngine` with chunking beyond 64 questions; decision ledger (`debugassist.core.ledger`, SQLite dev / Postgres verified).
- CLI: `debugassist decide | templates | modes`. Docs: `docs/decisions.md`.
- Tests: 75 mock-mode tests (conformance, limits, retries, breaker, chunking, two-stage, ledger, CLI) + 3 live tests (Clef, Clef-flash, LLM baseline) — all passing. Live fixtures: success for both models and three real error responses (400 missing field, 422 model mismatch, 422 one-option choice).

**Verify**
```
make check                                   # mock mode
DA_LIVE_TESTS=1 uv run pytest packages/decisions/tests/test_live.py
uv run debugassist decide D05 --state '{"error":"TypeError at routeDeepLink","flag":"notif_router_v2 5%"}'
```

**Findings**
- OpenRouter default routing for gpt-oss-120b sometimes returns whitespace-padded or unparseable structured output; pinning hosts + `require_parameters` fixed it in testing.
- macOS: every file created inside a dot-directory under `~/Desktop` gets the hidden flag, and Python 3.13 skips hidden `.pth` files (editable installs vanish). Fix: `make sync` installs a `sitecustomize.py` path hook, and uv now uses its managed CPython (Homebrew's Python ships its own `sitecustomize`). Moving the repo out of `~/Desktop` would also avoid it.
- Template packaging for wheels/PEX is deferred to P11 (templates are read from `packages/decisions/templates/`).
