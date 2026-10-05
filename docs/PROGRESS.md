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

## P3 — Walking skeleton (2026-10-04 → 05) — done

**Done**
- Fixed LangGraph pipeline (`debugassist run <VIT-id|latest>`): ingest → triage (D01, CODEOWNERS, Jira) → context collector (evidence bundle from 4 MCP servers) → RCA agent (D05) → mitigation (D11, policy-gated flag rollback) → reproduce + fix agents → validate → ship gate (D16) → PR + Jira. Checkpointed; `--resume <run> [--from-node fix]` restarts from a step without redoing earlier ones.
- MCP servers (FastMCP, stdio): code-search, crash-analytics, feature-flags (two-proportion z-test for flag ↔ crash correlation), git-history (previous release, commit window, bisect candidates).
- `LLMRunner` seam: `AgentRunner` (LangChain `create_agent` on OpenRouter, sandboxed coding tools, MCP tools, `submit_result` validated in the loop), `CassetteRunner` (replay), `ScriptedRunner` (mock; fixtures in `packages/llm/scripted/push-crash/`, derived from the live run below).
- Sandbox: git worktree per run + `docker run --network none` for commands; bash/path/egress guards; write policy (`configs/policies/writes.yaml`) with an audit log.
- Integrations: Jira Cloud (create/dedup by label, comment, transition, idempotent PR link, snapshot), GitHub (push to `debugassist/*`, open/update PR), Slack mock.
- Model is configuration (PLAN A11): capabilities and prices come from OpenRouter's `/models` (`core.openrouter`); structured output uses function calling when a model has no `response_format`.
- `debugassist report [run]` renders a run as one HTML page; `make demo-push-crash` (keyless), `make report`, `make screenshots`.
- Lint and pyright strict at 0 errors; 188 tests pass (live tests skipped without `DA_LIVE_TESTS=1`).

**Measured (live run `20261004-090058-vit-1001`, Nemotron 3 Ultra free via OpenRouter, Clef on Workers AI)**
- RCA correct: `routeV2` reads `state.session!.riderId` before hydration; suspect commit `d1f5020e1ab3` (removed `await whenHydrated()`); 8 claims, each citing evidence; 4 turns.
- Reproduction test fails on v1.6.1 with the production error; fix = one line (`await whenHydrated()`); failing-before exit 1, passing-after exit 0, suite exit 0.
- Clef: 4 decisions (D01 act, D05 act, D11 act → rollback dry-run, D16 escalate → draft PR), $0.00058 total. LLM: 264k tokens, $0 (free model). Final resumed run 294 s.
- Draft PR https://github.com/IshaanNene/miniride-client/pull/1 and Jira SCRUM-6 (In Review, PR linked).
- Mock mode: the same scenario end to end in 32 s with no keys.

**Done since (2026-10-04 evening)**
- Re-run on paid Nemotron 3 Ultra (OpenRouter) from the fix step: reproduction test fails on v1.6.1 with the production error, fix passes it, suite and the repo's lint/typecheck pass; the ship gate chose a ready PR. PR #1 now passes the target repo's CI (`client`, GitGuardian). That final run: $0.18, about 6 minutes end to end.
- Live agent progress and a watchdog (time limit per step, repeated-call detection, logged retries); the reproduction rule requires the production error (timeouts rejected); the fix step may repair a broken test while every check re-proves the contract.
- Run screenshots 08–18 (report, PR, diff, checks, Jira) in `docs/screenshots/`.

**Closed out (2026-10-05)**
- PII redaction before every LLM and Clef call (agent prompt, every tool result, Clef state), with tests that check what the model and the backend actually receive.
- Agents are nudged to submit two turns before their cap; PR #1 marked ready for review (the ship gate's decision); keyless demo fixtures refreshed from the final live run.
- Task list for the remaining phases: `docs/TASKS.md`.

**GroqCloud (added 2026-10-04, PLAN A12 / ADR 0007)**
- Works live on the free plan: agent tool calls, strict structured extraction and LLM-decider decisions with `openai/gpt-oss-120b`.
- Free-plan limits (8K tokens/min incl. part of the output cap, 200K/day) are too tight for the reproduce/fix agents so far: with ~5K input tokens per request they cannot keep the buggy code, the store and an example test in view, and re-read files instead of finishing. Three attempts on VIT-1001 ended without a reproducing test (one test was written but passed on the buggy release and was never submitted). Budget handling, dropped-step notes and recovery from Groq-rejected turns are in place; the paid Dev tier or OpenRouter credits remove the constraint.
- Bug found on the way: after a PR, the fix step reset the sandbox to the bot branch (which holds the previous fix) instead of the release tag, so reproduction ran against fixed code. Fixed.

**Findings / fixes along the way**
- Paid OpenRouter models returned 402: the account has no credits (the $50 is a key cap). Switched to the free model (PLAN A11).
- OpenRouter keeps queued requests alive with whitespace, so HTTP read timeouts never fire: every model call now has a 300 s wall-clock bound and backoff retries; daily-quota 429s fail fast.
- **Bug, fixed:** agents created inside a pipeline node inherited the pipeline's checkpointer and thread, so a resume or retry reloaded a stale agent. Agents now run with `checkpointer=False`.
- Step limit was ~3 graph steps per turn but a turn takes ~5; agents were cut off early and their transcripts lost. Now 6/turn + 20, and state is streamed so failures keep the transcript.
- Earlier gpt-oss runs: a symptom-suppressing fix (optional chaining), a test asserting the buggy behaviour, and a test-only draft PR. The ship gate now requires a verified reproduction and a source change; the reproduce step rejects tests that don't fail or don't exist.
- Duplicate Jira ticket SCRUM-5 from an early run (dedup by label added since).

## P4 — All 11 MCP servers (2026-10-05)

**Done**
- Seven new servers: bug-reports (BugDrop), jira, tracing (Jaeger v3), logging (Loki), incidents, releases, metrics-profiles — 11 servers and 55 tools in total, all started over stdio and listed in a smoke test; every tool called against the live stack.
- Shared rules: evidence IDs on every result, pagination and result caps, PII redaction, read-only by default; writes (`jira.*`, flag rollback) go through `gated_write` → policy + audit log, dry-run by default (`jira.link` added to the policy).
- Pruning where the talk asks for it: logs collapse into templates with counts and first/last times, errors first (2,000 gateway lines → 3 groups in a live check); traces come back summarized (critical path, error spans, slowest spans) and searches go per entry operation so health checks can't crowd out real traffic.
- `.mcp.json` for Claude Code / Desktop; `docs/mcp.md`; 15 recorded live responses (`tests/fixtures/live`, scanned for secrets) and offline tests that replay them.

**Findings**
- Health checks every few seconds filled Jaeger's "latest N traces" window, so filtering after the fetch returned nothing; searching per server-side operation fixed it.
- The log template masked `13` but not `13ms` (no word boundary), so timing-only differences didn't collapse; fixed with a test.
- The new servers are not yet wired into the agents' tool lists; P5/P6 (collector, evidence loop, subagents) decide which agent gets which server.
