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

## P7 — Mitigation, fix, validation, D11–D15 (2026-10-05) — done, one acceptance item partly met

**Done** (`pipeline/fixplan.py`, `pipeline/e2e.py`, fix/validate nodes)
- Fix plan, decided once before the first attempt:
  - D12 localization: code lists candidate functions from the RCA location, stack frames, files the RCA mentions, files changed in the release that introduced the bug, and callers of what the RCA names. Clef picks the location (two-stage when there are more than 40).
  - The commits in that release window that touched the chosen file are listed for the fix agent and the run summary. This closes P6's suspect-commit gap.
  - D13 strategy: "needs a human" escalates at the ship gate; "flag only" skips the fix only if the flag really was rolled back.
  - D14 tier: the ladder starts at the chosen tier, climbs, then falls back to the cheaper tiers. E2E is left out when it can't run.
- E2E tier: the agent writes a Playwright spec and checks it with a `run_e2e` tool. The pipeline builds the worktree in the network-less sandbox (cached by source state) and runs the spec in the official Playwright image on an internal Docker network that reaches only the MiniRide backends (no internet; verified). The captured environment (reported network profile, device, flag exposure from the report or crash event) is emulated with `e2e/support/emulate.ts` (CDP network/CPU throttling, visibility, flag overrides, script-time metric), which ships with the test.
- Failing-before / passing-after, the suite and the repo's CI checks run per tier. `--resume` now continues a run stopped by `--until`.
- Mitigation reports a flag already at 0% instead of a pointless dry-run rollback.

**Live results** (GitHub/Jira/Slack mocked, stopped after validate)
- BUG-001 (BD-1002): D12 → `EtaPoller.refreshLocally`; window commit `8d0f4fa` (the right one); D13 lifecycle/backgrounding. Unit test of ticks while hidden fails on the release and passes with the fix; suite and CI checks green. Fix stage about $0.06.
- BUG-002 (VIT-1001): D11 rollback p=0.955 with z=10.9 (dry-run). D12 → `routeV2` of 41 candidates (two-stage); window commit `d1f5020`. D14 chose E2E; it did not reproduce, the ladder fell back to unit, and the unit test failed and then passed with the fix; suite and CI checks green. About $0.26.
- BUG-003 (BD-1003, reporter on 2g / rtt 1950 ms / 250 kbps): RCA right (fresh idempotency key per retry); D12 → `requestRide`; window commit `c811fa9`. Playwright E2E with the reporter's network fails on the release. Both fix attempts reused the key but kept the 3 s timeout, so on that network every attempt still times out and the E2E still fails. **Validation not passed.** About $0.60.

**Findings**
- Two-stage D12 sent `path::function` as Clef question ids; Clef only accepts `[A-Za-z0-9_.-]`. Fixed with opaque ids and a test through the real engine.
- Vitals crashes carry the flag exposure on the event, not a report; the captured environment now reads both. Without it, the E2E ran with the flag off and could not reproduce.
- Without a way to run its spec, the E2E agent only "submitted" at the turn cap and got one rejection with no turns left; `run_e2e` fixed that.
- Playwright's attachment listings buried the error; they are stripped.
- The scratch dir first chosen (`.debugassist/`) collides with the tracked `.DebugAssist/` on macOS (case-insensitive); it is now `.da-e2e/`.

## P8 — Ship gate, PR / Jira / chat, post-merge watch, D16–D17 (2026-10-05) — done

**Done**
- **Chat replaces Slack** (the user's workspace isn't free): `integrations/chat.py`.
  - A Discord channel webhook (`DISCORD_WEBHOOK_URL`, `DA_MODE_CHAT`), checked against Discord's docs: `?wait=true`, content ≤ 2,000 chars, ≤ 10 embeds.
  - Otherwise the local mock inbox (`.data/mock/chat/inbox.jsonl`).
  - Text is PII-redacted and `allowed_mentions` is empty. Every message goes through the write gate and the audit log, and a chat outage never fails a run.
- **PR description from the `pr-authoring` skill**: its template block fixes the sections, and empty sections drop out with their heading. The PR now shows:
  - links to the Vitals issue or BugDrop report and the ticket;
  - the commit that introduced the bug, found in the release window;
  - every claim with its evidence IDs and grounding mark;
  - mitigation stats;
  - a test-proof table (tier, failing before, passing after, suite, CI checks) and "draft" when validation did not pass;
  - risk and rollback.
- **Links back to the source issue**: Vitals and BugDrop gained `POST …/links` (stored once per URL and shown on their pages), and BugDrop reports gained a status. The PR and ticket are linked after shipping, and the report moves to `in_progress`.
- **Post-merge watch (D17)**: the graph's last node leaves a run with a PR in `watching`. `debugassist watch <run>` then checks, in order:
  - merged (GitHub when live);
  - deployed (`make deploy REF=…` records `.data/deploys.jsonl`);
  - enough sessions since the deploy;
  - the issue's rate in equal windows before and after the deploy (new Vitals `/api/stats`; BugDrop reports per session).

  D17 then decides to resolve, keep watching or reopen, and code acts: Vitals or BugDrop resolved, Jira moved to Done (or back to In Progress), a rolled-back flag restored only with approval, and a chat message.

**Verified**
- Keyless BUG-002 demo end to end: dry-run rollback (5%→0%), verified unit fix, mock PR with the new body, PR linked on VIT-1001, chat to on-call, run left `watching` ($0).
- `make deploy` of the bot branch, the push-tap scenario and normal traffic, then `debugassist watch`: affected-session rate **0.025 (480 sessions) → 0.0 (260 sessions)**. Live Clef D17 `close_issue` p=0.96; VIT-1001 resolved, ticket → Done, chat sent. No flag restore (the rollback was a dry run).
- Discord has not been exercised live: there is no webhook URL yet. The payload is tested against a mock transport.

**Findings**
- The keyless demo stopped after RCA: new decisions shifted the mock's pseudo-random answers and D5 came out non-actionable. The demo now pins category, rollback, strategy, tier and ship outcome (still labelled mock).
- The first watch attempt tried to comment on mock ticket `MOCK-1` in the real Jira (404, nothing written) because it rebuilt integrations from `.env`. The watch now uses the run's own backends (mock ticket → mock Jira, mock PR → mock GitHub), and Jira errors are reported per action instead of aborting.

## P9 — Dashboard (2026-10-05) — done

**Done**
- **API** (`packages/api`, FastAPI on :8400, `make api`): a read layer over what runs leave on disk (state, node updates, agent logs, E2E artifacts), the decision ledger (read-only SQLite), the chat inbox and feedback. It also joins Vitals issues and BugDrop reports with their latest run. `GET /api/runs/{id}/stream` pushes graph changes and new agent calls as server-sent events until the run stops. Placed under `packages/` to follow the workspace convention (PLAN sketched `apps/api`).
- **Dashboard** (`apps/dashboard`, Next.js 16 App Router + Tailwind 4 + React Flow 12, `make dashboard`), built against the docs bundled with Next 16 (async `params`, generated `PageProps`, dynamic rendering). Screens:
  - Inbox: issues with priority, severity, owner and on-call; Clef D1 probabilities on hover; the latest run.
  - Issue / RCA: root cause on the left (category and confidence, location, window commit, flag, key facts with grounding badges, mitigation, fix and PR); evidence timeline and evidence list on the right; 👍/👎 with a comment, per RCA and per claim.
  - Run view: the fixed plan as a React Flow graph (deterministic gray, LLM blue, Clef amber) with subagent lanes, live over SSE; every agent call; the decision ledger (probability bar against thresholds, band, action, backend, latency, cost); turns and cost per LLM node.
  - PR panel: diff, validation proof, Playwright artifacts.
  - Metrics: pipeline outcomes per LLM mode, and per-decision volume, bands, backends, latency and $/1k. Accuracy and Brier appear only once outcomes are labelled.
  - Marketplace: skills with token footprint, agent types, subagents, templates.
  - Chat inbox.
- No web fonts are fetched, so it builds offline. CI gained a dashboard job (typecheck, lint, build).

**Verified** in the browser against the live stack and real runs:
- Inbox with all five issues.
- BUG-001's run (graph, four subagent lanes, 77 agent calls, the ledger including D12–D14), its RCA page and window commit.
- BUG-002's PR panel (diff and proof), Metrics and Marketplace.
- A mock run watched live: nodes advanced from `fix` to `open_pr` without a reload, then the page refreshed its ledger when the stream ended.
- No console errors. API tests: 8.

**Not yet**
- Diff fixer, Ask AI and Open-in-machine are shown disabled (P10).
- The Phoenix link opens the project, not the run (runs don't emit traces yet).
- Metrics shows no accuracy or calibration until P11 labels decisions.
- Mock runs are badged "scripted, not evidence" in Metrics.

## P10 — Post-PR features and the feedback loop, D18 (2026-10-05) — done

**Done**
- **Diff fixer** (`pipeline/postpr.py`, `debugassist fix-diff`, PR-panel box): an agent revises the committed fix in the run's sandbox per one instruction. The same fix contract is re-proved — now factored out as `nodes.fix_contract_problem` — before it commits, pushes to the bot branch and comments on the PR (policy-gated). From the dashboard it runs as a background job (`POST /api/runs/{id}/diff-fix`, polled).
- **Ask AI** (`debugassist ask`, PR-panel chat): seeded with the RCA, claims, timeline, evidence, fix and proof. Only evidence IDs that exist are kept as citations; invented ones are reported. Sessions are JSONL and resumable. A message marked as a correction goes through D18.
- **Open in your machine** (`debugassist open`, button): writes a devcontainer and a compose override for the run's worktree, pinned to the bad release and the fix branch, with the user's flags and the failing test, and returns a `vscode://` link.
- **D18 feedback loop** (`pipeline/feedback.py`, run in the background when a reaction arrives):
  - A bare 👍/👎 labels the ledger rows behind what was rated (RCA → D05; claim → its D09 check), so Metrics can show accuracy and Brier.
  - Comments are classified: root cause / location → labels and the prompt-improvement log; fix approach / style → the lesson appended to the fix skill on a local `debugassist/skill-…` branch with a marketplace PR record; other → the owner in chat.
- The fix step now loads the skills its agent type lists (`skills: {fix: [web-client-fixes]}`). The new `web-client-fixes` skill holds generic conventions only, so no catalog fixes leak into prompts.

**Verified (live LLM and live Clef; mocked GitHub for the demo PR)**
- **Diff fixer** on the BUG-002 demo PR, CLI and the dashboard's job path: two revisions committed after re-validation (`7ac88bc`, `2465792`), pushed and commented on the mock PR. About $0.03 each.
- **Ask AI** on BUG-001 and BUG-002: correct, cited answers for about $0.005.
- **D18:**
  - A style correction was classified `style` (p=0.94) → proposal branch `debugassist/skill-web-client-fixes-ed21a0cc` with the lesson.
  - A fix-approach correction scored p=0.595, under τ=0.6 → escalated to the on-call in chat, as designed.
  - A 👍 on a BUG-001 claim labelled its D09 row (`correct: true`).
- Tests: 6 new pipeline tests and 1 API test.

**Findings**
- The contract check reverted "the source change" with `git diff HEAD`. Once a fix is committed (diff fixer), HEAD already contains it, so every revision was rejected as "no longer reproduces". It now diffs against the release tag.
- Claim ↔ D09 matching compared against `json.dumps` output, which escapes quotes and non-ASCII characters. It now compares instruction text.
- A new run on the same issue reuses the bot branch and removes the older run's worktree; Open-in-machine reports this instead of failing.
- A proposal cut from HEAD can't see an uncommitted skill; it falls back to the working copy (after this commit, proposals are one-line patches).

## P11 — Harness (2026-10-05) — done

**Done** (`packages/harness`)
- **Agent types** (`configs/agent_types/*.yaml`, validated by a Pydantic model): `web-crash`, `backend-error`, `perf-regression`, `user-bug-report`. Each sets per-node limits, MCP servers and skills; preferred subagents; the validation ladder; its runtime image; and the marketplace ref. Resolution order: `--agent-type`, then the most specific match on source, kind, repo and language, then the target repo's `default_agent_type`, then web-crash. The type is chosen at ingest and re-applied on resume.
- **Marketplace**: exactly five plugins, each with a `plugin.yaml` (owners, version) and skills: `pr-authoring`, `test-planning`, `web-client-fixes`, `backend-fixes`, `perf-and-battery`.
  - It is fetched at a pinned git ref into `.data/marketplace/<sha>` (`working` means this checkout; `DA_MARKETPLACE_REF` overrides).
  - `make lint-skills` checks the plugin count, frontmatter, listings, per-node token budgets, and references to bug ids or ground truth.
  - `CONTRIBUTING-SKILLS.md` explains how to add skills and domains.
- **Progressive disclosure**: a node's prompt lists skills by name and description; the agent calls `load_skill(name)` for a body, within the node's token budget. Used by classify_rca, reproduce, fix and the diff fixer.
- **Domain extensions**: `marketplace/domains/{rider,dispatch,payments,platform}` with owners and components. Domain subagents join the pool D7 picks from (merged with the agent type's preferences); knowledge-base docs are loadable as `kb/<domain>/<doc>`. The KB was checked against the code (two docs corrected).
- **Packaging and launching**:
  - `debugassist harness pex <type>` builds a Linux PEX from the locked workspace in a `python:3.13-slim` container and stores it in MinIO under `pex/<type>/<commit>[-dirty].pex`.
  - `harness image <type>` builds the runtime image (Python, git, Docker CLI, PEX).
  - `harness run <issue>` runs the pipeline in the type's container: on the compose network, with the checkout mounted at the same path (`DEBUGASSIST_ROOT`), the Docker socket for sandboxes, service names via env, and the host's `DA_*` settings passed through.
  - Redis + Arq: `harness enqueue`, `make worker`, `POST /api/runs`.
- Decision templates ship inside the wheel; MCP servers start through the PEX (`PEX_MODULE`) when packaged; service URLs in deps and nodes are env-driven.

**Verified**
- `make lint-skills` is clean (5 plugins, 5 skills, 4 domains; at most ~580 tokens per node).
- The resolver picks the right type for each issue shape.
- PEX built (102 MB) and uploaded; image `debugassist/runtime-perf-regression` built (619 MB).
- **In the container**, a live RCA of VIT-1002: the harness resolved `perf-regression` itself (kind `perf`). Subagents used MCP tools, and the RCA agent loaded `perf-and-battery` and `kb/rider/module-map` on demand. Result: `src/eta/poller.ts → refreshLocally`, commit `8d0f4fa`. $0.08.
- **Worker**: an enqueued VIT-1002 was processed by a burst worker in its runtime container.
- 277 tests (8 harness, 1 runner).

**Findings**
- The first PEX build copied the whole checkout. Files under `targets/` failed with "Resource deadlock avoided": the checkout is on an **iCloud-synced Desktop**, which leaves unreadable placeholders and `* 2` conflict copies. The build now copies only the Python workspace.
- Inside a PEX, file-relative paths (repo root, decision templates) and `python -m` for MCP servers don't work. Fixed with `DEBUGASSIST_ROOT`, templates packaged into the wheel, and `PEX_MODULE`.
- Docker Desktop here has no host networking, so the runtime container joins the compose network and uses service names; links shown to people stay on localhost.
- Skills were written by someone who has seen the bug catalog (generic guidance only, linted). P13 evaluations should include a skills-off ablation. One perf hint close to a catalog fix was removed.
- D1 named `dispatch` as owner of a client perf issue (VIT-1002) — a triage-quality item for P13.

## P16 — Langfuse (2026-10-10) — done

**Done**
- `make langfuse`: self-hosted Langfuse v4 on :3200 (compose profile `langfuse`: web, worker, ClickHouse; Postgres, Redis and MinIO are the stack's own). A project and its API keys are created on first start (local-only dev credentials).
- `DA_TRACING=phoenix|langfuse|both|0` (`core/tracing.py`): the same OpenInference spans go to Phoenix, to Langfuse's OTLP endpoint (`/api/public/otel/v1/traces`, Basic auth, `x-langfuse-ingestion-version: 4`), or both. Each backend is used only when it answers; Langfuse also needs `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`.
- `debugassist eval langfuse --runs …` (`evals/langfuse_export.py`): each sweep becomes a Langfuse experiment (v4 replaced dataset runs), one item per scored run — input (the issue), output (the agent's root cause, outcome, validation), expected output from the catalog — with scores for root cause (1 / 0.5 / 0), category, validated, hidden tests, cost and turns. Ids are deterministic, so a re-export updates in place.
- The dashboard links a run's Langfuse trace next to Phoenix.

**Verified** (local Langfuse 4.56): the keyless demo run `20261010-104820-vit-1001` arrived as one trace of 57 observations (15 LLM generations, 7 tools, 7 agents) under its run id as session; the fix-quality and context-lean sweeps arrived as two experiments of 8 items, each with input, output, expected output and 5–6 scores, and a second export changed nothing but the names. A probe span with `DA_TRACING=both` reached Phoenix and Langfuse. `make check`: 362 tests.

**Findings**
- With `both`, the first version lost every Phoenix span: Phoenix's `TracerProvider.add_span_processor` removes its own exporter unless `replace_default_processor=False`. Caught by checking Phoenix after the demo run; regression test added.
- On v4 the v1 observations API returns 404 (`events_only` mode); read with `/api/public/v2/observations`.

## P15 — Context engineering: lean arm (2026-10-10) — measured, kept opt-in

**Done** (commits `8f1d596`, `1ae93f2`)
- `DA_CONTEXT=lean` (`core/ablation.py`), eval config `context-lean`: every file read (workspace and code-search MCP) is capped at 120 lines with a pointer to `outline_file`; `outline_file` lists symbols with line numbers (`core/outline.py`, TS/JS, Python, Go); long `run_command` output keeps failure lines and the last 40 lines, the full log behind `read_log`. Only offered in the lean arm, so the baseline's tool list and cache prefix are unchanged.
- `debugassist eval context --name <arm>` writes one audit per arm; the report renders them as *Context by arm*.
- Sandbox output decodes as UTF-8 with replacement (a stray byte no longer loses a command's result).

**Verified** (`evals/reports/2026-10-10`, the fix-quality bugs re-run, one seed): no token saving — input per run rose and `read_file`'s share went up (more, smaller reads); cost about level on a higher cache rate; outcomes within one-seed noise. See the report's arm and context tables.

**Findings**
- The first lean version applied the window only to range-less reads; agents always name a range, so it did nothing. Caught in the first run's transcript; that row is excluded.
- BUG-017's run took the e2e tier (D14) and three full-length fix attempts — most of the arm's token total. Read per-bug rows before averages.
- BUG-013 was wrong this time although the file it needed (110 lines) was read whole: run variance, not the cap.
- Next (ROADMAP P15): clearing old tool results and compaction with notes; repeated seeds.

## Fix quality (2026-10-10) — done

**Done** (commit `85cb379`; found by reading the failed runs of the cross-repo arm)
- **Python sandbox:** dispatch pins `python-preference = "only-managed"`, so uv downloaded its interpreter into the container's `$HOME` at install time and every later (offline) container had none — no dispatch test ever ran. `UV_PYTHON_INSTALL_DIR` now lives in the worktree.
- **Eval retry loop:** `--until validate` ended each run after its first validation, so no evaluated run ever got a second fix attempt. Eval runs stop after the ship gate (retries and the ship decision included; `outcome_ok` is now measured).
- **Edit tool:** a unique block that matches apart from indentation is applied and re-indented; a miss shows the closest lines; paths resolve repository- or component-relative (escapes still blocked, tested). A gateway fix had spent 14 of 20 turns on exact-match failures; across the 25-bug runs `edit_file` failed 51% of the time.
- **Report hygiene:** reports count only `openai/gpt-6-luna` runs; decision metrics and the replay use only decisions logged by the runs in the report.

**Verified** (`evals/reports/2026-10-10`, fix-quality arm, eight bugs): hidden tests passing 0 → 5 of those bugs (BUG-004, 013, 015, 016, 019); validated 75%; category right 8/8; turns per run 26.2 → 18.8 on the same bugs; ~$0.015 per run. `make check`: 339 tests.

**Findings**
- One seed is noisy: BUG-014 was solved end to end in the cross-repo arm and missed here (the RCA agent escalated without a location).
- BUG-020: fix planning's strategy decision (D13) chose "needs a human" (p = 0.9) for a contained one-function bug — a decision template to revisit.
- BUG-017 (CORS) still needs gateway-side evidence.

## P14 — Cross-repo investigation and hand-off (2026-10-10) — done

**Done**
- `pipeline/crossrepo.py`: investigation agents get read-only worktrees of every other target repo at its deployed release (`CODE_REPOS`). After RCA, if the location names another known target repo and the file exists there, the fix steps move: a new sandbox in that repo at its deployed release, the matching component and toolchain from its `.DebugAssist/pipeline.yaml`, and its default agent type; recorded as `run.handoff`.
- The RCA prompt says which repos exist and that where a bug is seen is not always where it lives (generic, no catalog hints).
- `debugassist eval context` (P15 audit): splits agents' input tokens into fixed prefix, re-sent tool results (per tool) and own messages. First audit: 53% re-sent tool results (`read_file` 32%), 35% prefix, 82% cache hits.
- Eval rows record `arm` and `commit`; reports group by arm. The README card shows a before → after panel for re-run arms.
- The LLM decider also retries connection errors.

**Verified** (`evals/reports/2026-10-10`, the six services bugs reported from the app): root cause right or close 0/6 → 5/6; BUG-014 (gateway payload) and BUG-019 (payments tariff) fixed end to end with hidden tests passing. `make check`: 336 tests.

**Findings**
- Three of the five correctly localised bugs got a fix that did not validate after the hand-off (one failed the gateway's typecheck) — fix quality in a second repo is the next item.
- BUG-017 (CORS) is invisible from the client: browsers report only `Failed to fetch`, so the agent never inspected the gateway's CORS settings. Needs gateway-side evidence (preflight logs) in the bundle.
- One run failed on a transient LLM-decider connection error; it is now retried, and the run was excluded and rerun.

## P13 — Evaluation harness + ablations (2026-10-07) — done

**Done**
- `packages/evals`: `debugassist eval estimate|run|label|replay|report`, `make eval`, `make eval-report`.
  - `run` triggers each bug once (reset → inject → scenario → discovery) and runs every configuration and seed on the same issue, with GitHub/Jira/chat forced to mock. It refuses when the estimate is above `--max-usd` (default 5).
  - `score`: RCA verdict (exact / directional / wrong) against the catalog location, expected outcome, hidden tests on a copy of the run's worktree, diff similarity to the reference fix, time and cost.
  - `labels`: deterministic correctness labels for D01, D05, D11, D12, D14 and D16 from ground truth, written to the ledger.
  - `metrics`: accuracy, Brier, reliability bins, ECE, latency and $/1k per decision. `replay` (E1) re-decides logged states with each Clef model and a rules baseline.
  - Ablation switches in `core/ablation.py`: `DA_DECIDER` (routed | clef | clef-flash | llm), `DA_ABLATE` (D3, D8, D9, D12, D14), `DA_LLM_SEED`.
- **Catalog: 25 bugs.** BUG-009..020 are code regressions in the client (TS), gateway (TS), dispatch (Python) and payments (Go): locale and currency edge cases, schema/field-name drift, a nil map, a tariff typo, dropped filters, CORS parsing and an ETA branch. Each is a natural-looking commit that passes the target repo's lint and tests, with a hidden test and a reference fix. BUG-021..025 are not our bug: carrier congestion with an SRE incident, a WebView-only crash, an ETA complaint about intended behaviour, a flag misconfiguration (rollback is the mitigation) and a bad vendored Vitals SDK sync (route to developer-platform).
- Simulator: `symptom_report` (riders look for one symptom and the first to notice reports it; optional network profile and always-report) and `device_crashes` (crash reports from a device we cannot emulate); `normal_traffic` takes a city, hold time and report text.

**Verified**
- `make verify-scenarios`: 25/25 (regression applies, hidden test fails on it, reference fix passes the repo's tests). `make check`: 328 tests.
- Discovery: every new bug's trigger was run on the live stack (inject → traffic) and produced a Vitals issue or BugDrop report (17/17 after the fixes below).

**Live evaluation (2026-10-07, `evals/reports/2026-10-07/report.md`)**
- All 25 bugs end to end on `openai/gpt-6-luna` (PLAN A13), one seed, ~$0.02 per run; a Nemotron arm (mostly RCA-only) from before the switch; an E1 replay of 149 labelled decisions across Clef, Clef-flash, the LLM decider and rules.
- Fixed on the way (each found by a live run): D2 dedup made the evaluator investigate a duplicate; mitigate acted on LLM free text as a flag name; OpenRouter routing (`require_parameters` + json_schema/seed/parallel_tool_calls) pinned Nemotron to one overloaded host; the LLM decider had no backoff and too few tokens; the Go sandbox's login shell dropped Go from PATH; the scorer credited client paths to services modules. Prompt-cache hits are now measured (79% on gpt-6-luna) and priced.
- Main finding: services bugs reported only through the app are localised in the client repo — next work item.

**Findings**
- Many first ideas for regressions were caught by the target repos' own lint or tests (deprecated `utcnow`, an analytics test without props, GraphQL coercing numeric strings, an idempotency-key test). Discarded: a catalog bug that CI catches is not realistic.
- First discovery sweep: 12/17. Fixed:
  - A render error inside a route is caught by react-router's error page, so it never reaches the app's crash handler or Vitals. Riders now treat that page as a crash and report it; BUG-009 and BUG-011 are discovered through BugDrop.
  - `normal_traffic` aborted when a crash killed a booking mid-flow; that is now the rider's outcome.
  - Flag injections now wait for propagation (services poll Unleash every 5 s); BUG-024's riders were quoting before the 100% rollout reached payments.
  - Concurrent bookings race onto the same free driver, so a market never fills up. BUG-015 books one rider at a time.
  - BUG-020 books a long trip (Ferry Building → SFO); the regression shows a few-minute countdown during a ~49-minute ride.
- Scoring earlier live runs: BUG-001's RCA is directional and the hidden test fails (the agent's fix still ticks every 5 s), and BUG-003 was classified with the wrong category.

## P12 — Observability, cost, guardrails, privacy (2026-10-05) — done

**Done**
- **Phoenix tracing** (`core/tracing.py`; arize-phoenix-otel + OpenInference). Each `debugassist run` is one trace:
  - a root AGENT span tagged with `session.id = run id`, so resumes group into one session;
  - a span per graph node;
  - the LangChain instrumentor's LLM and tool spans (MCP tools included);
  - Clef DECISION spans with the redacted input state, chosen values, p, band, action, backend and cost;
  - TOOL spans for sandbox commands (exit code, output tail) and AGENT spans for subagents.

  The trace id is saved on the run and the dashboard links straight to it. Tracing switches on when Phoenix answers and DA_TRACING≠0; otherwise every helper is a no-op (tests, CI).
- **Global run budget** (`pipeline/budget.py`): LLM spend (per node) plus Clef spend (ledger) against the agent type's `run_budget_usd`. An LLM node does not start once it is spent, and each agent's `max_budget_usd` (RCA, subagents, reproduce, fix) is lowered to what is left. The run view gains a "Cost by node" card (LLM nodes and Clef per decision).
- **Prompt-injection hygiene** (`core/untrusted.py`): issue titles, user reports, evidence, subagent findings, validation and test output, diffs and the Ask-AI context are fenced in `<untrusted_data source=…>` blocks; a closing tag inside the data cannot end the fence. The runner's system note says never to follow instructions inside them.
- **Fixtures** (`tests/fixtures/injection`: a malicious report with PII, injected log lines, a code comment addressed to AI agents) and 12 tests:
  - injected text appears only inside fences;
  - PII never reaches the model (email, phone, card, precise GPS, bearer key);
  - the commands it asks for are blocked (`git push origin main`, `curl … $(cat .env)`, `printenv`, `docker`, `gh`);
  - secret paths and escapes are refused;
  - the write policy denies pushing `main` or opening PRs elsewhere.

**Verified** — live run `20261005-122328-vit-1002` (perf-regression, $0.17): RCA → plan → unit reproduction → fix → validation passed (fails before, passes after, suite and CI checks). In Phoenix it is one trace of 413 spans: 40 LLM, 66 TOOL (26 sandbox commands; MCP `commit_details`, `find_references`, `query_logs`), 21 DECISION, 5 AGENT (run, classify_rca, fix, two subagents), plus every node. The deep link `…/projects/<id>/traces/<trace id>` resolves. 290 tests.

**Findings / not done**
- The instrumentor also traces each agent middleware hook (~280 CHAIN spans per run): noisy but harmless.
- Raw tool outputs inside Phoenix spans are not redacted. Phoenix is self-hosted and only LLM/Clef inputs leave the machine, which are redacted; an OpenInference TraceConfig could mask them if Phoenix ever runs remotely.
