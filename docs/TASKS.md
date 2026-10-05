# DebugAssist — task list

Status against `docs/SPEC.md` (with `docs/PLAN.md` §0 amendments), audited 2026-10-05. One phase at a
time; a phase is done when its tests pass, its `make` target works, `docs/PROGRESS.md` is updated and
the work is committed. Legend: `[x]` done · `[~]` partly done · `[ ]` not started.

Overall: P0–P7 done, P8–P14 not started (a few pieces pulled forward). Next: P8.

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
- [~] Slack ping for P0/P1 to the mock inbox (inbox UI comes with the dashboard, P9)
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

## P8 · Ship gate, PR / Jira / Slack, post-merge (D16–D17)
- [x] D16 ship gate (verified repro + source change required; draft without proof); PR + Jira link/comment/transition
- [ ] `pr-authoring` skill-driven PR description (summary, root cause, evidence, proof, risk, rollback plan)
- [ ] Link the Vitals / BugDrop issue; Slack DM (real or mock inbox UI)
- [ ] `post_merge_watch` + D17: after merge + `make deploy`, watch crash/report rates, resolve or reopen, restore flag

## P9 · Dashboard (Next.js + Tailwind + React Flow)
- [ ] Inbox · Issue/RCA page (RCA left, evidence timeline right) · Run view (graph, ledger, turns, cost, Phoenix link)
- [ ] PR panel (diff, proof, diff fixer, Ask AI, open-in-machine) · Metrics · Marketplace & agent types

## P10 · Post-PR features + feedback (D18)
- [ ] Diff fixer · Ask AI chat (resumable, cites evidence) · Open in your machine (devcontainer / compose override)
- [ ] D18 correction triage → label store, proposed skill update PR, prompt improvements

## P11 · Harness
- [~] Agent types: `web-crash` (add `backend-error`, `perf-regression`, `user-bug-report`; optional `flaky-test`)
- [x] `.DebugAssist/pipeline.yaml` in both target repos, read at run time
- [ ] Marketplace with exactly 5 plugins (pr-authoring, test-planning, web-client-fixes, backend-fixes, perf-and-battery);
      runtime fetch at a pinned ref; skill token budget; `CONTRIBUTING-SKILLS.md`; `make lint-skills`
- [ ] Skill loading for our runner (progressive disclosure: names + descriptions, `load_skill` tool) — PLAN A4
- [ ] Domain extensions (`marketplace/domains/<domain>/`: subagents, knowledge base, owners)
- [ ] PEX per agent type → MinIO; Docker runtime image per type; `debugassist run --agent-type`; Redis + Arq workers

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
