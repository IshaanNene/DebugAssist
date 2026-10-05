# DebugAssist — task list

Status against `docs/SPEC.md` (with `docs/PLAN.md` §0 amendments), audited 2026-10-05. One phase at a
time; a phase is done when its tests pass, its `make` target works, `docs/PROGRESS.md` is updated and
the work is committed. Legend: `[x]` done · `[~]` partly done · `[ ]` not started.

Overall: P0–P11 done, P12–P14 not started (a few pieces pulled forward). Next: P12.

## P3 · Walking skeleton ✅
- [x] BUG-002 end to end through every node to a real PR (target CI green) and a Jira ticket
- [x] 4 MCP servers (code-search, crash-analytics, feature-flags, git-history), sandbox, mock mode, run report
- [x] Redact PII before anything reaches the LLM or Clef (agent prompts, tool results, Clef state) — §11
- [x] Nudge agents to submit two turns before the cap
- [x] PR #1 marked ready for review (the ship gate's open_pr decision)
- [x] Submodule pointers verified at `main` (the working tree is on the scenario branch by design)
- [x] Keyless demo fixtures refreshed from the final live run (unedited)

## P4 · All 11 MCP servers (§5) ✅
- [x] code-search · crash-analytics · feature-flags · git-history
- [x] bug-reports (BugDrop): list_reports, get_report, get_logs, get_screenshots (+ get_screenshot_image), get_ui_state_timeline
- [x] jira: get, find_open (dedup), create, comment, link PR, transition (Jira Cloud or mock; writes gated)
- [x] tracing (Jaeger v3): find_traces (health checks excluded), get_trace summarized, service_dependencies
- [x] logging (Loki): query_logs with pruning (repeats collapsed, errors first), log_stats, log_patterns
- [x] incidents: list_active_incidents, incident_details, dependency_status
- [x] releases: list_releases, release_diff, version_adoption, rollout_status, last_good_and_first_bad
- [x] metrics-profiles: promql (summarized), service_profile, session_perf (client CPU/wakeups/long tasks)
- [x] Evidence IDs, pagination, result caps, PII redaction, read-only defaults in every server; writes gated + audited
- [x] `.mcp.json` (11 servers, 55 tools, verified over stdio); `docs/mcp.md`; recorded live fixtures + offline tests

## P5 · Triage + context collector (D1–D4) ✅
- [x] D1 triage (priority, severity, owner, customer impact, worth a run); CODEOWNERS + catalog; Jira create + dedup by label
- [x] D2 dedup over *older* open Vitals issues + recent BugDrop reports (+ none); a duplicate is commented on the open ticket and the run stops
- [x] D3 relevance scoring of optional windows; kept by action then score, leftover budget to "background or better"; pruned list kept in state
- [x] D4 vision questions over a report's images (≤ 4), findings as evidence + ledger
- [x] Collector: BugDrop ingest (`BD-…`), core evidence + optional windows (session, perf samples, trace, logs around the event, incidents, adoption, report log rings); isolated per source
- [x] Chat page for P0/P1: Discord webhook (free) or the mock inbox (inbox UI comes with the dashboard, P9)
- [x] Live Clef verification of D2/D3/D4 (after the token's IP filter was widened)

## P6 · Root cause (D5–D10) ✅
- [x] RCA agent with evidence-cited claims; D5 categorization
- [x] Early exit with a routed RCA for non-actionable categories (incident, third-party, device): low effort, no fan-out, straight to the ship gate as `rca_only`
- [x] D6 evidence loop (need more data? which source next?), ≤ 2 rounds, every fetch deterministic
- [x] D7 fan-out + parallel subagents (≤ 4) from `configs/subagents.yaml`: breadcrumb-analyst, crash-correlator, commit-bisector,
      flag-correlator, trace-analyst, log-analyst, incident-checker, screenshot-analyst, perf-profiler, code-localizer (pruned inputs)
- [x] D8 rabbit-hole monitor as agent middleware (Clef check every 6 tool calls: continue / warn / stop early)
- [x] D9 grounding check per claim — one Clef call per claim with only its cited evidence (drop/flag unsupported claims)
- [x] D10 effort routing by difficulty
- [x] Accept: BUG-001 RCA names the hot loop and ~17 min backgrounding; BUG-002 names the flag and the race
- [x] Suspect commit for BugDrop reports: P7 lists the commits in the release window that touched the chosen fix location

## P7 · Mitigation + fix + validation (D11–D15) ✅ (one acceptance item partly met)
- [x] D11 flag correlation (z-test) + policy-gated rollback (dry-run); supervised interrupt; "already at 0%" is reported, not rolled back
- [x] Reproduce → fix → validate with failing-before / passing-after, suite, repo CI checks; D15 retry ≤ 3
- [x] D12 fix localization: candidates from the RCA, stack, release diff and callers; two-stage over many; Clef-safe ids
- [x] Commits in the release window that touched the chosen location (closes P6's suspect-commit gap)
- [x] D13 fix strategy choice ("needs a human" escalates; "flag only" only if the flag was actually rolled back)
- [x] D14 validation tier + ladder: from the choice upwards, then cheaper tiers; E2E left out when it can't run
- [x] E2E tier: Playwright (official image) against a build of the worktree on an internal Docker network (no internet),
      captured environment (network profile, CPU, visibility, flag exposure) via `e2e/support/emulate.ts`; `run_e2e` tool
- [x] Accept: BUG-001 fixed with a background-loop test (fail → pass, suite + CI checks green)
- [x] Accept: BUG-002 rollback recommended (dry-run per policy) + unit fail → pass (E2E tried first, fell back)
- [~] Accept: BUG-003 reproduced by a throttled-network Playwright E2E (fails on the release), but both fix attempts
      only reused the idempotency key and kept the 3 s timeout, so the E2E still fails — validation not passed
- [ ] Follow-up: make the fix step use every RCA fact (here: "times out after 3 s, shorter than matching takes"),
      e.g. pass grounded claims, not just the summary, to the fix agent; re-run BUG-003 with retries

## P8 · Ship gate, PR / Jira / chat, post-merge (D16–D17) ✅
- [x] D16 ship gate (verified repro + source change required; draft without proof); PR + Jira link/comment/transition
- [x] `pr-authoring` skill (`marketplace/plugins/core/skills/pr-authoring/SKILL.md`): its template drives every PR
      description — summary, links, root cause + window commit, evidence with grounding marks, mitigation, fix,
      test proof table (tier, fail → pass, suite, CI checks), risk & rollback
- [x] Link the PR / ticket back on the Vitals issue or BugDrop report (new `links` endpoints; BugDrop report status)
- [x] Chat instead of Slack (not free): Discord channel webhook (`DISCORD_WEBHOOK_URL`) or the local mock inbox;
      PII-redacted, mentions disabled, policy-gated + audited; a chat outage never fails a run
- [x] `post_merge_watch` + `debugassist watch <run>` + D17: after merge + `make deploy REF=…`, compare the issue's
      rate in equal windows before/after (Vitals `/api/stats`, BugDrop reports per session); resolve (Vitals,
      BugDrop, Jira → Done, restore a rolled-back flag behind approval, chat) or reopen
- [x] Keyless demo runs every node end to end (`make demo-push-crash`), then deploy + watch resolves the issue
- [ ] README logo wall still shows Slack (needs a Discord icon in `docs/assets/icons`)

## P9 · Dashboard (Next.js + Tailwind + React Flow) ✅
- [x] API (`packages/api`, :8400): runs, run detail + graph status, agent calls, decision ledger with template policy,
      E2E artifacts, feedback, issues (Vitals + BugDrop joined with runs), chat inbox, metrics, marketplace; SSE stream
- [x] Inbox: source, priority/severity, owner/on-call, Clef D1 probabilities on hover, run outcome
- [x] Issue / RCA page: RCA left (category + confidence, location, window commit, flag, key facts with grounding
      badges, mitigation, fix + PR); evidence timeline + evidence list right; 👍/👎 + comment per RCA and claim
- [x] Run view: React Flow pipeline graph (gray/blue/amber), live over SSE, subagent lanes, every agent call,
      decision ledger (probability bar vs thresholds, band, action, backend, cost), turns and cost per LLM node
- [x] PR panel: diff viewer, validation proof (fail → pass, suite, CI), Playwright screenshots/video
- [x] Metrics: pipeline outcomes per LLM mode; per-D# volume, bands, backends, latency, $/1k, accuracy/Brier when labelled
- [x] Marketplace & agent types: skills (token footprint, used by), agent types, subagents, decision templates
- [x] Chat inbox screen; `make dashboard`; CI job (typecheck, lint, build)
- [x] Diff fixer, Ask AI, Open-in-machine (P10)
- [ ] Per-run Phoenix deep link once runs emit traces (observability phase); accuracy/calibration need P11 labels

## P10 · Post-PR features + feedback (D18) ✅
- [x] Diff fixer: one instruction → agent in the run's sandbox → the fix contract re-proved (fails on the release,
      passes with the change, suite + CI checks) → commit, push to the bot branch, PR comment (policy-gated);
      `debugassist fix-diff`, dashboard box with presets (background job)
- [x] Ask AI: chat seeded with RCA, claims, evidence, fix and proof; cites only known evidence ids; resumable
      sessions (`debugassist ask --session`); a message marked as a correction goes to D18
- [x] Open in your machine: devcontainer + compose override pinned to the bad release and the fix branch, flags at the
      user's exposure, failing test command, `vscode://` link (`debugassist open`)
- [x] D18: bare 👍/👎 → ledger labels (RCA → D05, claim → its D09); root cause / location → labels + prompt log;
      fix approach / style → lesson appended to the fix skill on a local `debugassist/skill-…` branch with a
      marketplace PR record (this repo is outside the push policy); other / low confidence → owner in chat
- [x] Fix step loads its agent type's skills (`skills: {fix: [web-client-fixes]}`), so approved lessons reach the next fix
- [ ] Warm container pool / remote "open" (stretch)

## P11 · Harness ✅
- [x] Agent types: `web-crash`, `backend-error`, `perf-regression`, `user-bug-report` — limits, MCP servers, skills per
      node, subagent preferences, validation ladder, runtime image, pinned marketplace ref; resolved per issue
      (`--agent-type` → most specific match → the target repo's `default_agent_type` → web-crash)
- [ ] Optional `flaky-test` agent type
- [x] `.DebugAssist/pipeline.yaml` in both target repos, read at run time
- [x] Marketplace with exactly 5 plugins (pr-authoring, test-planning, web-client-fixes, backend-fixes, perf-and-battery);
      fetch at a pinned git ref (`DA_MARKETPLACE_REF`); per-node skill token budget; `CONTRIBUTING-SKILLS.md`;
      `make lint-skills` (plugin count, frontmatter, listings, budgets, no evaluation answers)
- [x] Skill loading for our runner with progressive disclosure: names + descriptions in the prompt, `load_skill` tool
- [x] Domain extensions (`marketplace/domains/<domain>/`: owners, components, subagents joining D7's pool, knowledge base)
- [x] PEX per agent type (built in a Linux container) → MinIO; runtime image per type; `debugassist run --agent-type`;
      `debugassist harness run` in a container; Redis + Arq workers (`make worker`, `POST /api/runs`)
- [ ] PEXes/images built so far: perf-regression (the others build the same way)

## P12 · Observability, cost, guardrails, privacy
- [x] Bash / path / egress guards; write policy + audit log; redaction at BugDrop intake and before every LLM/Clef call; untrusted-input marking
- [x] Live agent progress + watchdog (wall clock, repeated calls, logged retries)
- [ ] Phoenix traces for full runs (OpenInference LangChain instrumentor; Clef + MCP + bash spans)
- [ ] Global run budget; cost per node in the run view; redaction tests on agent inputs

## P13 · Evaluation harness + ablations
- [~] Bug catalog: 8 bugs (BUG-001..008) → at least 25 across TS / Python / Go, incl. "not our bug" cases
- [ ] `make eval`: reset → inject → traffic → discovery → pipeline → score (RCA exact/directional, fix, time, cost)
- [ ] Decision metrics per D# (accuracy, Brier, ECE, latency, $/1k); calibration; JSONL export
- [ ] Ablations: no Clef · Clef-flash only · Clef only · routed; D3/D8/D9/D12/D14 on/off; ≥3 seeds
- [ ] `evals/reports/<date>/report.md` + CSV + charts (ask before any run estimated above $5)

## P14 · Polish
- [x] Visual README, diagrams, screenshots, demo GIF (no unmeasured numbers)
- [ ] `make demo-battery`, `make demo-weak-network`; `docs/demo-script.md`; `docs/RESUME.md`; `docs/INTERVIEW-NOTES.md`
- [ ] README: §1-item mapping table; "where Clef changes decisions" with measured deltas; eval results from reports
