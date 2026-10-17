# Engineering roadmap: 100 tasks

The engineering work left after the 2026-10-16 audit and its fixes (`115c744`, `eea8dc1`, `379fed9`). It
complements [ROADMAP.md](ROADMAP.md), which holds the research questions (does Clef help, fix width, real bugs).
Each task says when it is done; `[x]` means done (see the Progress section at the end).

Marks: **$** needs live LLM or Clef spend (the OpenRouter key is capped; anything over $5 is asked first),
**D** needs Docker or the private `miniride-services` submodule, **G** needs a real GitHub App or repository.
Tasks without a mark can be done and checked offline with `make check`.

## A · Security and the sandbox boundary

- [x] **001** Prompt-injection red-team catalogue: ≥30 payloads (issue bodies, logs, commit messages, code comments)
  as fixtures under `evals/redteam/`, each with the action it tries (escape, exfiltrate, ungated write).
- [ ] **002** Canary secrets for the red team: unique values in a fake `.env`, `$HOME` and the App key path; a scorer
  that searches every LLM request, comment, PR body, ticket and trace of a run for them.
- [ ] **003** $ D Red-team arm: run 001 against the live pipeline, three seeds; report escapes, canary leaks and
  ungated writes (target 0/0/0) under `evals/reports/`.
- [x] **004** Offline red-team checks that need no model: every payload's commands go through `check_command`, its
  paths through `confine`/`walk_files`, its text through the untrusted fence — a test per payload.
- [x] **005** Per-run context instead of `os.environ` (audit P3-15): run id, mode and code repos passed explicitly
  to tools and MCP processes; two runs built in one process keep separate values (test).
- [x] **006** Authentication on the API's mutating endpoints: a token (`DA_API_TOKEN`) required on every POST;
  the dashboard sends it; tests for missing and wrong tokens.
- [x] **007** Bind the API to 127.0.0.1 by default (`make dashboard`), and refuse to start on another interface
  without `DA_API_TOKEN`.
- [ ] **008** Narrow the runtime image's `safe.directory '*'` to the mounted checkout path, with a test that the
  image config names no wildcard.
- [x] **009** Secret scanning in CI (gitleaks or an equivalent pinned tool) over the diff of each push and PR.
- [ ] **010** D Container image scan (Trivy or equivalent) of the runtime images in CI, failing on critical CVEs.

## B · Correctness and validation

- [x] **011** Error-signature matching by exception type plus message pattern instead of a substring, with tests for
  messages that vary by runtime and for assertions that merely contain the text.
- [ ] **012** Reproductions for bugs with no exception (a wrong value): require a failing assertion that names the
  reported value; tests for both kinds.
- [x] **013** Route away from a fix only when the RCA's category agrees with D05 or carries high confidence
  (ROADMAP P18: a wrong "not ours" was terminal); tests for agree / disagree / confident.
- [x] **014** `test_one` reads its harness config from the release like `test`/`lint`/`setup` (audit: two sources);
  one reader for all of them.
- [x] **015** Validation records which checks ran with which command and config hash, stored on the attempt.
- [x] **016** A fix that deletes or skips existing tests (`skip`, `xfail`, `.only`) is flagged and forces a draft;
  tests for each marker in Python, TypeScript and Go.
- [x] **017** The ship gate refuses `open_pr` when the diff touches more files than the fix plan's location set
  allows (a configurable slack); tests.
- [ ] **018** Crash safety of `fix`: kill between phase one and phase two, resume, and the worktree is consistent
  (test with the toy repo from `test_proof_path.py`).
- [x] **019** Idempotent `pr_and_notify`: a resumed run does not commit twice, push twice or post a second comment
  (test with recording fakes).
- [ ] **020** Mitigation for rider reports (D11 abstains outside crash rates): a report-based signal and tests.

## C · Testing

- [x] **021** Coverage gate in CI: `pytest-cov` with a floor on `pipeline/` (start at today's number, never lower).
- [ ] **022** Mutation testing (`mutmut`) on `_repro_problem`, `fix_contract_problem`, `ship_gate`, the release
  checks; a make target and a recorded score; target ≥85% killed.
- [x] **023** Property tests (Hypothesis) for `redact_secrets`/`redact_text`: no secret-shaped input survives, no
  plain diagnostic text is mangled.
- [x] **024** Property tests for `confine`, `walk_files` and `hostgit.trusted_gitdir` over generated trees with
  symlinks, `..` and odd names.
- [ ] **025** Contract tests: recorded GitHub, Jira, Workers AI and OpenRouter responses replayed against the clients
  (fixtures under `tests/fixtures/`), with the live variant behind `DA_LIVE_TESTS=1`.
- [ ] **026** A webhook-to-PR test on the mock App: a signed delivery queued, polled, run with the scripted runner,
  ending in a draft PR and one marker comment.
- [ ] **027** Fault-injection tests: Clef 5xx and time-outs, LLM 429 and hung streams, an MCP server crash mid-run;
  the fallback reason lands in the ledger and the run ends cleanly.
- [x] **028** Graph tests for every routing edge (`after_rca`, `after_mitigate`, retry cap) generated from the graph
  definition, so a new edge without a test fails.
- [x] **029** Flakiness guard: the suite runs three times in CI weekly with random order (`pytest-randomly`) and
  reports any test whose result changes.
- [x] **030** A test that every action in `writes.yaml` has a call site that goes through `PolicyGate` (static scan),
  and no call site writes without one.

## D · Architecture and code health

- [ ] **031** Split `pipeline/nodes.py` (≈1,800 lines) into `pipeline/nodes/` with one module per node and the
  shared helpers in their own modules; public names unchanged.
- [x] **032** Remove the hidden import cycle: `postmerge` and `feedback` stop importing `nodes._notify`; a shared
  `notify` module.
- [ ] **033** Typed records for `FixPlan.location/strategy/tier` and `Validation.attempts` instead of dicts.
- [ ] **034** Errors as typed records (`node`, `type`, `message`, `traceback`) instead of string pairs read by
  index (`graph.py` reads `[-2]`).
- [x] **035** A CI check that the count of `dict[str, Any]` and `pyright: ignore` in `pipeline/` only falls.
- [ ] **036** One `Workspace` object for all host access to a run's worktree (git, reads, walks), replacing the
  helpers spread across modules.
- [ ] **037** Decision layer behind one interface with deciders chosen per template from config (rules, LLM, Clef);
  no behaviour change by default.
- [ ] **038** $ Per-template decider choice from replay with confidence intervals; D01 and D14 on rules if the
  replay still says rules win.
- [ ] **039** Delete or isolate packaging that the evaluated path never uses (document what PEX, MinIO and Arq
  are for, or move them behind an extra).
- [ ] **040** An ADR for the concurrency model: what may share a process, what a run owns, what the poller owns.

## E · Performance and scale

- [x] **041** Per-node latency profile: p50/p95 per node from `timings_ms` across stored runs, as a CLI command and
  a report section.
- [ ] **042** Tool-call latency in the trace summary: time spent in MCP, sandbox and model per run.
- [ ] **043** Start an agent's MCP servers in parallel (one task owns all sessions) instead of one after another.
- [ ] **044** Cache the collector's evidence per (issue, release) so a resumed or re-run issue does not refetch.
- [x] **045** `api/data.runs` reads an index file instead of parsing up to 500 `state.json` files per request.
- [ ] **046** A worker pool for the App poller with one run per repository at a time and idempotent run keys.
- [x] **047** Rate-limit awareness for GitHub: read `X-RateLimit-Remaining`, back off before exhaustion; test.
- [ ] **048** Sandbox install cache shared across runs of the same lockfile (content-addressed), measured.
- [ ] **049** $ A benchmark job that replays cassettes on a fixed machine and fails if a node's p50 regresses >10%.
- [ ] **050** A stated scale target (runs per hour, repositories) in `docs/github-app.md`, with the bottleneck named.

## F · Reliability and observability

- [x] **051** Structured JSON logs for the poller and the pipeline CLI (one schema, run id on every line).
- [x] **052** Counters for runs started, failed, retried and their cost, written per poll pass to `.data/app/metrics.json`
  and exposed on the API.
- [ ] **053** An alert rule: failure ratio over the last N App runs above a threshold posts to chat (gated).
- [x] **054** An operations runbook in `docs/github-app.md`: start, stop, read logs, rerun, revoke the key.
- [x] **055** `_extract` stops swallowing exceptions: they are logged and recorded on the result.
- [x] **056** Health endpoint that checks its dependencies (ledger DB, queue dir writable, App reachable) separately.
- [x] **057** Retention: run directories older than N days are pruned (state kept, worktrees and logs removed).
- [x] **058** Every persisted file under `.data/` passes `redact_secrets` on write (a single writer helper), with a test
  that scans a run directory for credential shapes.
- [x] **059** The CLI summary prints fallbacks, budget stops and gate denials as a one-line health verdict.
- [x] **060** Trace attributes for the gate: every `PolicyGate.gated` call becomes a span with verdict and outcome.

## G · API, data and schema

- [x] **061** `schema_version` on `state.json`, with upgraders for older versions and a test on a stored old file.
- [ ] **062** Alembic migrations for the ledger instead of `create_all`; an upgrade test from a stored old database.
- [ ] **063** Typed response models for every API endpoint (FastAPI `response_model`), so the dashboard's types can
  be generated.
- [ ] **064** Generate the dashboard's TypeScript API types from the OpenAPI schema in CI and fail on drift.
- [x] **065** Pagination on `/api/runs` and `/api/issues` (cursor), with limits enforced server-side.
- [x] **066** The audit log as JSON Lines with a schema and a reader (`debugassist audit show --run …`).
- [ ] **067** Ledger outcome labels written back when a PR merges or is closed (D17 already watches).
- [x] **068** A state-file reader that tolerates partial writes (write to temp, rename) for `state.json` and node files.
- [x] **069** Atomic `seen.json` updates in the poller (temp file + rename) and a lock against two pollers.
- [x] **070** Deterministic SVG output in reports (`svg.hashsalt`, no date metadata) so regeneration is byte-exact.

## H · GitHub App and integrations

- [ ] **071** G Create the App and run it on one consenting repository; record the first run's outcome.
- [ ] **072** Installation webhooks (`installation`, `installation_repositories`) refresh the repo map immediately.
- [ ] **073** A PR comment loop for App repositories (review comments → diff fixer), gated and draft-only.
- [ ] **074** CI failures as input: a failed check run on a default branch becomes an issue-like input.
- [x] **075** Per-repository budgets in `pipeline.yaml` (and a global cap), enforced before a run starts.
- [x] **076** `debugassist app rerun GHA:owner/repo#n` that clears the seen entry and queues a run.
- [ ] **077** A team catalog for real repositories: CODEOWNERS-based owner instead of MiniRide teams.
- [ ] **078** Discord notifier tested against a recorded real webhook response (fixture), with rate-limit handling.
- [ ] **079** Jira client retries and idempotency keys for comment and transition (a resumed run does not double-post).
- [ ] **080** DebugAssist as an MCP server for coding agents (`investigate VIT-1001` → RCA and proof), mock mode first.

## I · Evaluation and research

- [x] **081** Wilson 95% intervals on every rate in the generated report.
- [x] **082** McNemar tests for paired arms in the report, and a rule: a difference is claimed only when supported.
- [x] **083** Pre-registered thresholds: an arm file states its success threshold before it runs; the report checks it.
- [ ] **084** $ Live arm with the full call-variations check on the five real bugs (ROADMAP P18).
- [ ] **085** $ Live bisect arm on the real bugs that have a good release.
- [ ] **086** Non-pytest runners for bisect's per-case step (vitest `-t`, `go test -run`), tested on toy repos.
- [ ] **087** Two TypeScript and two Go real-bug cases following the ROADMAP's checklist (no model needed to add).
- [ ] **088** Catalog growth: one concurrency bug and one data-migration bug with hidden tests (`make verify-scenarios`).
- [ ] **089** $ Rework D01, D13 and D14 and re-measure with three seeds on both arms (ROADMAP P18).
- [ ] **090** A baseline agent arm (a plain tool-using agent, no plan) on the catalog, for comparison.

## J · Documentation, developer experience and CI

- [x] **091** A guarantees table in the README: each promise links to the test that enforces it.
- [x] **092** A doc check in CI: stated limits in docs (timeouts, caps) are compared with the constants in code.
- [ ] **093** Move the quickstart above the results in the README and split the 41 KB README into linked pages.
- [x] **094** `docs/THREAT-MODEL.md`: assets, actors (reporter, maintainer, model), trust boundaries, controls, tests.
- [x] **095** A contributor guide: workspace layout, adding a package, adding an MCP tool, adding a decision.
- [x] **096** `make doctor`: checks Python, uv, Docker, submodules, `.env` keys present (names only), ports free.
- [x] **097** Pre-commit hook for the loopback check and for secret-shaped strings in staged files.
- [x] **098** Release notes generated from conventional commits (`git-cliff` or a script) per phase.
- [ ] **099** CI caches for pnpm and uv tuned, and the job time recorded; target under 5 minutes total.
- [x] **100** A fresh-clone check in CI: `make bootstrap && make check` on a clean runner, timed.

## Progress

- 2026-10-17: 006, 007 (POSTs need the dashboard's Origin or `DA_API_TOKEN`; `API_HOST` off loopback refuses to
  start without a token), 021 (`make coverage` in CI: total ≥76%, `pipeline/` ≥74%; today 77% and 75%), 055,
  061 (`schema_version` 2 with a v1 upgrader), 068, 069 (atomic writes; one poller at a time), 070, 081.
  Not run here: the dashboard's typecheck and lint (Node tools hang on this machine; CI runs them).
- 2026-10-17: 001, 004 (32 payloads in `evals/redteam/payloads.yaml`, each with the control that must stop it;
  64 offline checks; only `container` waits for the live arm 003), 016 (added skip/xfail/`.only`/`t.Skip` lines and
  `pyproject.toml`, `setup.cfg`, `package.json` changes force a flagged draft), 030 (a static scan; it found the
  poller's "not onboarded" and "failed" comments posted without the gate, now gated, and the diff fixer's comment
  not audited, now audited), 032 (`pipeline/notify.py`), 054 (Operations in `docs/github-app.md`), 076
  (`debugassist app rerun`), 094 (`docs/THREAT-MODEL.md`).
- 2026-10-17: 005 (`core.runctx`: run id, mode and code repos per asyncio task; nothing in `pipeline/` writes
  `os.environ`), 014 (`test_one` read from the release like the other commands), 019 (a resumed PR step makes no
  empty commit and posts no second issue comment), 023, 024 (Hypothesis property tests for redaction, `confine`,
  `walk_files` and the git-dir check), 047 (GitHub rate limits raise `RateLimited` with the wait; the poll waits it
  out), 082 (exact McNemar test per pair of configurations in the report).
- 2026-10-17: 009, 097 (`scripts/check_secrets.py`, the redaction patterns as a pre-commit hook and a CI step over
  tracked files), 013 (a "not ours" RCA ends the run only when D05 picked the same category), 015 (each validation
  attempt records its commands and a hash of the release's harness config), 035 (`test_typing_ratchet.py`:
  233 `dict[str, Any]`, 9 `pyright: ignore` in `pipeline/`, may only fall), 041 (`debugassist eval latency`; on
  this machine's 75 stored runs since 2026-10-14: `classify_rca` p50 135 s / p95 214 s, `fix` 159 s / 449 s, whole
  run 347 s / 656 s), 057 (`debugassist prune`, dry run unless `--apply`; 35 old worktrees, 8.96 GB here, not
  deleted), 058 (every string in node files and `state.json` is redacted on write), 092 (docs cite limits as
  `` `NAME` = value ``; a test compares them with the code), 096 (`make doctor`).
- 2026-10-17: 011 (the reported error must appear as `Type: message` with numbers and addresses free; a test that
  only asserts the text no longer counts; the bisect replay is unchanged: semver#484 → `d8813b67a2`, 3/3), 028
  (`test_graph_edges.py`, 38 cases read from the built graph), 052 (`.data/app/metrics.json`, `GET
  /api/app/metrics`), 056 (`GET /api/health/deps`), 060 (a guardrail span per gate record), 066 (`debugassist
  audit`; tests no longer write to the real audit log), 083 (`evals/arms/*.yaml`, checked in the report), 091 (a
  guarantees table in the README), 095 (`docs/CONTRIBUTING.md`).
- 2026-10-17: 017 (more than 2 changed source files outside the plan's focus and the RCA's location make the PR a
  draft, with the files named), 029, 100 (`.github/workflows/weekly.yml`: the suite three times compared by
  `scripts/flaky.py`, and `make bootstrap && make check` on a clean runner, timed; not run yet), 045, 065 (the run
  list reads `runs/.index.json`, re-parsing a state file only when its size or mtime changed — 0.67 s cold, ~0 s
  warm over this machine's 323 runs; `before=<run id>` pages), 051 (`.data/logs/<component>.jsonl`), 059 (`health`
  line in the run summary), 075 (`run_budget_usd` in a repository's `pipeline.yaml`, and `DA_RUN_BUDGET_CAP_USD`,
  default $5, under the agent type's budget), 098 (`scripts/changelog.py`).
  Partly done, still open: 026 (a signed webhook reaches exactly one `debugassist run`, tested; the run itself to a
  draft PR is covered separately in `test_proof_path.py`, not in one test) and 027 (Clef 5xx, time-out and open
  breaker fall back with the reason in the ledger; an MCP server crash and a hung model stream are not tested yet).
