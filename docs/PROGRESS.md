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

## P5 — Triage + context collector (2026-10-05) — done

**Done**
- BugDrop reports are first-class issues: `debugassist run BD-1001` ingests the report (description, device, flags, network, files) and triages it (owner by Clef when there is no stack).
- D2 dedup at triage over open Vitals issues and recent BugDrop reports (plus "none"). A confident duplicate is commented on the existing ticket and the run stops (`status: duplicate`) instead of starting a second investigation.
- Collector (`pipeline/collector.py`): core evidence always kept; optional windows — the session, its perf samples, the linked trace, logs from each service in the 10 minutes around the event (`query_logs(around=…)`), active incidents, dependency status, version adoption, and for reports their log rings — scored by D3 and kept by action then score within a 12k-token budget. What was pruned (with scores and why) stays in the run state. Each source is isolated, so one being down is a note, not a failed run.
- D4: Clef vision questions over a report's images (blank screen, error dialog, which screen, abnormal battery use); the findings become evidence and the decision is in the ledger.
- The run summary now shows dedup, evidence kept/pruned, screenshot findings, and **which backend made the decisions** (with the reason for any fallback).

**Verified** with the keyless pipeline on VIT-1001 (17 kept / 2 pruned) and BD-1001 (13 kept, D4 ran), plus unit tests for D3 budget selection and the duplicate path.

**Live Clef check (after the token's IP filter was widened):**
- D4 on BD-1001's screenshot: screen `search` (correct — the "Where to?" home screen), blank p=0.08 (correct, the rider had reopened the app), abnormal battery p=0.007 (correct, no battery screenshot).
- D2 on BD-1001: VIT-1001 at p=0.61 → escalate band, run continued — a fair call: same symptom, but that rider had the flag off.
- D3 on VIT-1001: kept the crashing session and version adoption; pruned backend logs, OS/city breakdowns, incidents and dependency status — right for a client-side race.
- **Bug found and fixed:** D2 marked VIT-1001 (the original crash) as a duplicate of BD-1001, a report filed 1.5 hours later. Candidates are now only issues opened *before* the one being triaged; the earliest is canonical.
- D3 pruned more than the budget required; leftover budget now goes to windows scored "background" or better.
- Earlier the token was IP-restricted to an old address and every call returned 401 with a silent fallback; the run summary now reports the decision backend.

## P6 — Root cause, D5–D10 (2026-10-05) — done

**Done** (`pipeline/rca.py`, `configs/subagents.yaml`)
- D10 sets the RCA agent's reasoning effort by difficulty; non-actionable categories (incident, third party, device) get a short routed RCA with no fan-out and go straight to the ship gate.
- D6 evidence loop before the agent (at most 2 rounds): Clef decides whether more data is needed and from which source — related BugDrop reports, related Vitals issues, incidents, each service's logs around the event, session perf, last-good/first-bad. Each fetch is deterministic code, and a source already offered is not offered again.
- D7 picks up to 4 of 10 specialised subagents. Each gets only its slice of the evidence and a few MCP servers, runs in parallel with tight limits (8 turns, 12 tool calls, $0.10, 300 s), and returns findings with evidence IDs that the RCA agent consolidates.
- D8 checks the RCA agent's last 12 tool calls every 6 calls: continue, warn (a note is injected) or stop early.
- D9 grounds each claim separately against the evidence it cites. Supported claims are kept, unverified ones are flagged, unsupported ones are dropped (and listed in the run state). A citation to an ID no source returned is dropped without a model call.

**Live results**
- BUG-002 (VIT-1001): names `notif_router_v2` and the hydration race; subagents code-localizer, crash-correlator and commit-bisector; D9 kept 6 claims and flagged 1; about $0.03.
- BUG-001 (BD-1002, run `20261005-055140-bd-1002`, $0.12): "`refreshLocally()` does not update `this.last.at`, so each tick re-schedules with near-zero delay: ~286 wakeups/s while hidden" — `src/eta/poller.ts`. Subagents perf-profiler, log-analyst, trace-analyst and screenshot-analyst. D9: 8 supported, 1 unverified (p=0.65), 0 dropped, including the ~17 minutes hidden (0.99) and the code mechanism (0.97).
- Miss: that run named the file's initial commit as the suspect instead of the refactor that introduced the defect (an earlier run got it right). BugDrop reports have no last-good/first-bad window yet; P7's localization (D12) should close this.

**Findings**
- D9 at first dropped true claims for two reasons:
  - Batching every claim with all cited evidence into one Clef state lost track of which evidence belonged to which claim. True claims scored 0.03–0.27 batched and 0.87–0.99 alone, with a false control at 0.007. Fixed with one call per claim.
  - The evidence was truncated: tool results were kept only as 600-character previews, and lookups were capped at 1,500 characters. Tool calls that return an evidence ID now keep up to 6,000 characters for grounding.
- Evidence IDs for fetched items had used Python `hash()`, which changes between processes; they now use `evidence_id()`.
- Tests: `test_rca.py` covers per-claim grounding (and that each call sees only its own citations), the fuller tool text, D7 ordering and cap, and the D6 loop.
