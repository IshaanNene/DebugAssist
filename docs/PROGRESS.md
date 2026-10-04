# Progress

| Phase | Status | Date | Notes |
|---|---|---|---|
| P0 Plan & scaffold | ✅ done | 2026-10-04 | See below |
| P1 Decision engine | ✅ done | 2026-10-04 | See below |
| P2a Target system + telemetry | ✅ done | 2026-10-04 | See below |
| P2b Sources + catalog + simulator | ✅ done | 2026-10-04 | See below |
| P3 Walking skeleton | ⏭ next | | |

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

## P2a — Target system + telemetry (2026-10-04)

**Done**
- `IshaanNene/miniride-services` (private, v1.4.0): gateway (Node/TS GraphQL Yoga), dispatch (FastAPI + SQLAlchemy 2.0 + Postgres), payments (Go). Unit tests (gateway 5, dispatch 7, payments 6), `scripts/integration.sh`, Dockerfiles with healthchecks, CI, CODEOWNERS, `.DebugAssist/pipeline.yaml`.
- `IshaanNene/miniride-client` (public, v1.4.0): React 19 PWA — booking flow, notification center + launch-from-push deep links (router v1/v2 behind `notif_router_v2`), visibility-aware ETA poller, idempotent ride requests with timeout retries, OpenFeature/Unleash flags, OTel fetch tracing, batched analytics, crash screen. 18 vitest tests, 2 Playwright E2E tests, CI, CODEOWNERS, `.DebugAssist/pipeline.yaml`.
- Both repos added as submodules under `targets/`; `configs/catalog.yaml` (7 teams, on-call rotations, service → path ownership).
- Compose profile `target` (client, gateway, dispatch, payments) + OTel Collector (traces → Jaeger, logs → Loki OTLP, metrics → Prometheus remote write); Unleash dev tokens + `make flags` bootstrap (`notif_router_v2`, `surge_pricing` at 0% gradual rollout).
- Verified live: booking via Playwright; one trace spans miniride-client → gateway → dispatch (incl. SQL spans); gateway GraphQL operation logs and dispatch/payments logs in Loki; dispatch/payments/HTTP metrics in Prometheus.
- `docs/ARCHITECTURE.md` with the stand-in mapping table.

**Verify**
```
make up && make flags
make e2e                                              # Playwright: book a ride, open from push
bash targets/miniride-services/scripts/integration.sh
open http://localhost:8080  http://localhost:16686    # book a ride, then find the trace in Jaeger
```

**Findings**
- Jaeger 2.21 serves only the v3 query API, which streams one JSON document per trace.
- `opentelemetry-instrumentation-sqlalchemy` silently skips SQLAlchemy 2.1 → pinned 2.0.x.
- Node ESM apps need `module.register("@opentelemetry/instrumentation/hook.mjs")` or pino/graphql are never instrumented.
- Go: `resource.NewWithAttributes(semconv.SchemaURL, …)` conflicts with the SDK default schema → `NewSchemaless`.
- TypeScript pinned to 6.0.3 (typescript-eslint does not support TS 7 yet).

## P2b — Sources, catalog, simulator (2026-10-04)

**Done**
- **Vitals** (service + browser/Python/Go/Node SDKs), **BugDrop** (service + browser SDK with reporter UI), **incidents** service — compose profile `sources`; `debugassist.core.redaction` (shared PII redactor).
- MiniRide integrated both SDKs (client v1.5.0 → v1.5.2, services v1.5.0 → v1.5.1, each with `scripts/release.sh`); service versions now come from their manifests.
- `groundtruth/`: 8 bugs (TS ×5 incl. gateway, Python, Go, infra) with regression patches, reference fixes and hidden tests; `debugassist scenario verify` passes for all 8.
- `debugassist scenario inject|trigger|reset|verify|list|status`, `make trigger BUG=…`, `make reset-scenario WIPE=1`, `make verify-scenarios`, `make traffic`, `make load` (Locust), `make sync-sdks`.
- Simulator: Playwright fleet with device/locale personas, CDP latency/throughput, packet-loss retransmits, background emulation (Page Visibility API + page clock fast-forward), push launches, bug reports with generated attachments (OS battery panel).
- Tests: 137 Python + 10 SDK (vitest) + target repos (client 18 + 3 E2E, gateway 7, dispatch 8, payments 4 packages).

**Acceptance (measured on the local stack, 2026-10-04)**
- `make trigger BUG=001` → BugDrop BD-1001 with app screenshot + battery-panel attachment, 6 log rings (500 analytics events, 498 of them `eta_background_tick`), UI-state timeline with a 17.0-minute hidden interval; Vitals `background_cpu` issue (~215 wakeups/s, v1.6.0).
- `make trigger BUG=002` (240 sessions, 25% on the previous release) → Vitals crash group `TypeError … 'riderId'`, symbolicated to `routeV2 (src/notifications/router.ts:27)`; `notif_router_v2` exposed in 6.7% of all sessions vs 100% of crashing sessions; only v1.6.1 affected.
- All other scenarios (003–008) produce their discovery signals (see ARCHITECTURE.md table).

**Findings / fixes along the way**
- JS busy time understates a hot loop of cheap ticks (2.5% busy at ~250 wakeups/s): Vitals now flags sustained background **wakeups** as well as busy time.
- BugDrop lost reports from blank screens (empty screenshot → 415); SDK now captures the page and skips invalid images.
- Gateway threw `SyntaxError` on non-JSON upstream 500s (fixed in services v1.5.1).
- Weak-network duplicates only reproduce with packet loss, not latency alone (as in the talk's airport case).
- **Mistake, corrected:** a `git push --tags` in the target repos published local scenario tags (v1.6.0–1.6.4, v1.6.6); they were deleted from GitHub within minutes. Rule added to CLAUDE.md.
- DebugAssist is a public repo, so `groundtruth/` is public; isolation from agents is enforced at the sandbox (P3/P12), with a leak test on every regression patch.
