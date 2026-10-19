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
- [x] **002** Canary secrets for the red team: unique values in a fake `.env`, `$HOME` and the App key path; a scorer
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
- [x] **008** Narrow the runtime image's `safe.directory '*'` to the mounted checkout path, with a test that the
  image config names no wildcard.
- [x] **009** Secret scanning in CI (gitleaks or an equivalent pinned tool) over the diff of each push and PR.
- [ ] **010** D Container image scan (Trivy or equivalent) of the runtime images in CI, failing on critical CVEs.

## B · Correctness and validation

- [x] **011** Error-signature matching by exception type plus message pattern instead of a substring, with tests for
  messages that vary by runtime and for assertions that merely contain the text.
- [x] **012** Reproductions for bugs with no exception (a wrong value): require a failing assertion that names the
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
- [x] **018** Crash safety of `fix`: kill between phase one and phase two, resume, and the worktree is consistent
  (test with the toy repo from `test_proof_path.py`).
- [x] **019** Idempotent `pr_and_notify`: a resumed run does not commit twice, push twice or post a second comment
  (test with recording fakes).
- [x] **020** Mitigation for rider reports (D11 abstains outside crash rates): a report-based signal and tests.

## C · Testing

- [x] **021** Coverage gate in CI: `pytest-cov` with a floor on `pipeline/` (start at today's number, never lower).
- [x] **022** Mutation testing (`mutmut`) on `_repro_problem`, `fix_contract_problem`, `ship_gate`, the release
  checks; a make target and a recorded score; target ≥85% killed.
- [x] **023** Property tests (Hypothesis) for `redact_secrets`/`redact_text`: no secret-shaped input survives, no
  plain diagnostic text is mangled.
- [x] **024** Property tests for `confine`, `walk_files` and `hostgit.trusted_gitdir` over generated trees with
  symlinks, `..` and odd names.
- [x] **025** Contract tests: recorded GitHub, Jira, Workers AI and OpenRouter responses replayed against the clients
  (fixtures under `tests/fixtures/`), with the live variant behind `DA_LIVE_TESTS=1`.
- [x] **026** A webhook-to-PR test on the mock App: a signed delivery queued, polled, run with the scripted runner,
  ending in a draft PR and one marker comment.
- [x] **027** Fault-injection tests: Clef 5xx and time-outs, LLM 429 and hung streams, an MCP server crash mid-run;
  the fallback reason lands in the ledger and the run ends cleanly.
- [x] **028** Graph tests for every routing edge (`after_rca`, `after_mitigate`, retry cap) generated from the graph
  definition, so a new edge without a test fails.
- [x] **029** Flakiness guard: the suite runs three times in CI weekly with random order (`pytest-randomly`) and
  reports any test whose result changes.
- [x] **030** A test that every action in `writes.yaml` has a call site that goes through `PolicyGate` (static scan),
  and no call site writes without one.

## D · Architecture and code health

- [x] **031** Split `pipeline/nodes.py` (≈1,800 lines) into `pipeline/nodes/` with one module per node and the
  shared helpers in their own modules; public names unchanged.
- [x] **032** Remove the hidden import cycle: `postmerge` and `feedback` stop importing `nodes._notify`; a shared
  `notify` module.
- [x] **033** Typed records for `FixPlan.location/strategy/tier` and `Validation.attempts` instead of dicts.
- [x] **034** Errors as typed records (`node`, `type`, `message`, `traceback`) instead of string pairs read by
  index (`graph.py` reads `[-2]`).
- [x] **035** A CI check that the count of `dict[str, Any]` and `pyright: ignore` in `pipeline/` only falls.
- [x] **036** One `Workspace` object for all host access to a run's worktree (git, reads, walks), replacing the
  helpers spread across modules.
- [x] **037** Decision layer behind one interface with deciders chosen per template from config (rules, LLM, Clef);
  no behaviour change by default.
- [ ] **038** $ Per-template decider choice from replay with confidence intervals; D01 and D14 on rules if the
  replay still says rules win.
- [x] **039** Delete or isolate packaging that the evaluated path never uses (document what PEX, MinIO and Arq
  are for, or move them behind an extra).
- [x] **040** An ADR for the concurrency model: what may share a process, what a run owns, what the poller owns.

## E · Performance and scale

- [x] **041** Per-node latency profile: p50/p95 per node from `timings_ms` across stored runs, as a CLI command and
  a report section.
- [x] **042** Tool-call latency in the trace summary: time spent in MCP, sandbox and model per run.
- [x] **043** Start an agent's MCP servers in parallel (one task owns all sessions) instead of one after another.
- [x] **044** Cache the collector's evidence per (issue, release) so a resumed or re-run issue does not refetch.
- [x] **045** `api/data.runs` reads an index file instead of parsing up to 500 `state.json` files per request.
- [x] **046** A worker pool for the App poller with one run per repository at a time and idempotent run keys.
- [x] **047** Rate-limit awareness for GitHub: read `X-RateLimit-Remaining`, back off before exhaustion; test.
- [x] **048** Sandbox install cache shared across runs of the same lockfile (content-addressed), measured.
- [ ] **049** $ A benchmark job that replays cassettes on a fixed machine and fails if a node's p50 regresses >10%.
- [x] **050** A stated scale target (runs per hour, repositories) in `docs/github-app.md`, with the bottleneck named.

## F · Reliability and observability

- [x] **051** Structured JSON logs for the poller and the pipeline CLI (one schema, run id on every line).
- [x] **052** Counters for runs started, failed, retried and their cost, written per poll pass to `.data/app/metrics.json`
  and exposed on the API.
- [x] **053** An alert rule: failure ratio over the last N App runs above a threshold posts to chat (gated).
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
- [x] **062** Alembic migrations for the ledger instead of `create_all`; an upgrade test from a stored old database.
- [x] **063** Typed response models for every API endpoint (FastAPI `response_model`), so the dashboard's types can
  be generated.
- [x] **064** Generate the dashboard's TypeScript API types from the OpenAPI schema in CI and fail on drift.
- [x] **065** Pagination on `/api/runs` and `/api/issues` (cursor), with limits enforced server-side.
- [x] **066** The audit log as JSON Lines with a schema and a reader (`debugassist audit show --run …`).
- [x] **067** Ledger outcome labels written back when a PR merges or is closed (D17 already watches).
- [x] **068** A state-file reader that tolerates partial writes (write to temp, rename) for `state.json` and node files.
- [x] **069** Atomic `seen.json` updates in the poller (temp file + rename) and a lock against two pollers.
- [x] **070** Deterministic SVG output in reports (`svg.hashsalt`, no date metadata) so regeneration is byte-exact.

## H · GitHub App and integrations

- [ ] **071** G Create the App and run it on one consenting repository; record the first run's outcome.
- [x] **072** Installation webhooks (`installation`, `installation_repositories`) refresh the repo map immediately.
- [x] **073** A PR comment loop for App repositories (review comments → diff fixer), gated and draft-only.
- [x] **074** CI failures as input: a failed check run on a default branch becomes an issue-like input.
- [x] **075** Per-repository budgets in `pipeline.yaml` (and a global cap), enforced before a run starts.
- [x] **076** `debugassist app rerun GHA:owner/repo#n` that clears the seen entry and queues a run.
- [x] **077** A team catalog for real repositories: CODEOWNERS-based owner instead of MiniRide teams.
- [x] **078** Discord notifier tested against a recorded real webhook response (fixture), with rate-limit handling.
- [x] **079** Jira client retries and idempotency keys for comment and transition (a resumed run does not double-post).
- [x] **080** DebugAssist as an MCP server for coding agents (`investigate VIT-1001` → RCA and proof), mock mode first.

## I · Evaluation and research

- [x] **081** Wilson 95% intervals on every rate in the generated report.
- [x] **082** McNemar tests for paired arms in the report, and a rule: a difference is claimed only when supported.
- [x] **083** Pre-registered thresholds: an arm file states its success threshold before it runs; the report checks it.
- [ ] **084** $ Live arm with the full call-variations check on the five real bugs (ROADMAP P18).
- [ ] **085** $ Live bisect arm on the real bugs that have a good release.
- [x] **086** Non-pytest runners for bisect's per-case step (vitest `-t`, `go test -run`), tested on toy repos.
- [x] **087** Two TypeScript and two Go real-bug cases following the ROADMAP's checklist (no model needed to add).
- [ ] **088** Catalog growth: one concurrency bug and one data-migration bug with hidden tests (`make verify-scenarios`).
- [ ] **089** $ Rework D01, D13 and D14 and re-measure with three seeds on both arms (ROADMAP P18).
- [ ] **090** A baseline agent arm (a plain tool-using agent, no plan) on the catalog, for comparison.

## J · Documentation, developer experience and CI

- [x] **091** A guarantees table in the README: each promise links to the test that enforces it.
- [x] **092** A doc check in CI: stated limits in docs (timeouts, caps) are compared with the constants in code.
- [x] **093** Move the quickstart above the results in the README and split the 41 KB README into linked pages.
- [x] **094** `docs/THREAT-MODEL.md`: assets, actors (reporter, maintainer, model), trust boundaries, controls, tests.
- [x] **095** A contributor guide: workspace layout, adding a package, adding an MCP tool, adding a decision.
- [x] **096** `make doctor`: checks Python, uv, Docker, submodules, `.env` keys present (names only), ports free.
- [x] **097** Pre-commit hook for the loopback check and for secret-shaped strings in staged files.
- [x] **098** Release notes generated from conventional commits (`git-cliff` or a script) per phase.
- [x] **099** CI caches for pnpm and uv tuned, and the job time recorded; target under 5 minutes total.
- [x] **100** A fresh-clone check in CI: `make bootstrap && make check` on a clean runner, timed.

## Progress

- 2026-10-19: 048 (`integrations.installcache`: `Sandbox.install` on a fresh worktree looks up a key hashed from the
  image, the setup command, the component and every tracked manifest and lockfile; a hit copies the cached dependency
  directories in (clone on APFS, `--reflink` on Linux, never hard links), a miss installs and saves them before any
  agent runs. LRU, 8 entries; `DA_INSTALL_CACHE=0` turns it off. Measured by `scripts/measure_install_cache.py`
  (`evals/reports/install-cache.json`, outside iCloud): install against restore 3.5 s → 0.3 s (semver), 1.5 s → 0.0 s
  (go-runewidth), 9.4 s → 1.9 s (radashi); each suite passes offline after the restore as after the install.
  miniride-client was not measured: iCloud had evicted 96 of its git objects and did not bring them back.)
- 2026-10-19: 036 (`core.workspace.Workspace`: git through `hostgit`, every file through `guards.confine`, walks
  through `walk_files`; `Sandbox.workspace` gives the run's. The nodes, `release`, `bisect`, `usages`, `fixplan`,
  `e2e`, `postpr`, `deps`, the sandbox and both GitHub clients use it. It closed reads
  that skipped the guards: `usages` read every `git grep` hit by joining onto the worktree (a tracked symlink out of
  it could be followed), `fixplan` read the file the RCA named the same way. `test_workspace_only` fails on a new git call,
  worktree join or walk in `pipeline/`.)
- 2026-10-19: 031 (`pipeline/nodes/`: `intake`, `triage`, `context`, `classify`, `mitigation`, `fixing`, `checks`,
  `validation`, `ship`, `pr`, with shared helpers in `common` and `testing`. Moved mechanically by an AST script —
  definitions unchanged, imports derived; module names differ from the node functions so `nodes.fix` stays the
  function the graph looks up. Helpers used across modules got public names (strict pyright forbids private names
  across modules); the package exports every old name, the private ones as aliases, so no import changed.
  Tests that patched `nodes._sandbox` / `nodes.ROOT` patch each module's binding through `nodes.MODULES`. Three
  source scanners globbed `pipeline/*.py` non-recursively — the typing ratchet, the gated-writes scan and the
  `os.environ` scan — and would have silently stopped seeing the nodes; all three now use `rglob`.)
- 2026-10-19: 064 (`python -m debugassist.api.schema` writes the API's OpenAPI schema to `apps/dashboard/openapi.json`
  with stable formatting; `openapi-typescript` 7.13.0, pinned, generates `src/lib/api-schema.ts`; `make api-types`
  runs both. `types.ts` now takes `RunSummary`, `Health`, `HealthDeps` and `AppMetrics` from it — the hand-written
  `RunSummary` had drifted (non-null `status`, `issue_ref`; `source` without `"github"`). `test_openapi_schema_is_current`
  fails when the API's schema and the committed file differ; CI's dashboard job regenerates the types and fails on a
  diff. The dashboard's typecheck and lint run here again: the "Node tools hang" note above was iCloud having evicted
  3,081 files of `apps/dashboard/node_modules`; reinstalled from the lockfile.)
- 2026-10-19: 087 (REAL-006 shopspring/decimal#461 and REAL-007 mattn/go-runewidth#113 in Go, REAL-008
  radashi#482 and REAL-009 chrono#655 in TypeScript: recent issues closed by a merged PR with its own regression
  test; the parts of each report naming the cause or fix withheld and listed; upstream's tests verbatim as the hidden
  tests; each verified locally and in its sandbox image (`golang:1.26-alpine`, `node:22-alpine`) — fails on the
  release, passes with the upstream fix — and `scenarios.real.prepare` confirmed the fix and PR head unreachable.
  `test_real_cases.py` checks every case's files, commands and that the report does not name the fixed file or
  commit. Not run through the pipeline yet: that is 084/085-style live spend.)
- 2026-10-18: 025 (`scripts/record_contracts.py` records the read-only calls our clients make — GitHub branch,
  missing branch, PR list and PR; Jira's JQL search; OpenRouter's catalog entry for the model in use — redacted
  (e-mails, Atlassian identities, avatars, the Jira host) into `packages/integrations/tests/fixtures/contracts/`;
  `test_contracts.py` replays them against `GitHubLive`, `JiraCloud` and `openrouter.model_info`, and three `live`
  tests re-fetch them and check the fields we read, all passing today. Jira: this account's token sees no projects,
  so only the (empty) search is recorded; an issue snapshot needs a project it can read.)
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
- 2026-10-17: 002 (`evals/canary.py`: unique fake secrets in a `.env`, `~/.ssh/id_rsa` and an App key, and a scan of
  every file a run leaves; for the live arm 003), 008 (the runtime image no longer trusts every directory; the
  launcher sets `safe.directory` for the mounted checkout — not run under Docker here), 012 (a report that names no
  error needs a reproduction failing on an assertion), 040 ([ADR 0010](adr/0010-concurrency-model.md)), 050 (Scale
  in `docs/github-app.md`: about 10 issues an hour per poller at the measured median), 053 (more than half of the
  last 10 runs failed → one alert an hour through the gate), 072 (`installation` webhooks refresh the repository
  list before the next pass), 077 (a real repository's owner from CODEOWNERS, else its `pipeline.yaml`), 079 (Jira
  retries 429 and gateway errors, honouring Retry-After, and skips a comment already on the ticket).
  CI on `c0e5d47` failed the `pipeline/` coverage floor (72% < 74%); fixed in `9a5e1d3` with CLI and poll-loop tests.
- 2026-10-17: 027 (also a hung model call cut off by `MODEL_CALL_TIMEOUT_S`, and an MCP server that dies mid-call:
  `McpError: Connection closed` at once, not a hang), 026 (closed: the intake chain test and the proof-path graph
  test together cover delivery → run → draft PR), 039 (ARCHITECTURE: what PEX, MinIO, runtime images and the
  Arq worker are for, and that the evaluated path uses none), 042 (agents record wall time; `eval latency` splits
  time into model, sandbox, MCP and file tools — on the 75 stored runs, which predate wall time: sandbox p50 7.9 s,
  MCP 8.7 s, file tools 9.1 s per run), 063 (response models for runs, health and App metrics in the OpenAPI
  schema), 067 (D16 rows labelled `pr_merged` / `fixed_after_deploy` by the post-merge watch), 078 (Discord 429
  waited out; fixtures from Discord's documentation, not recorded live), 086 (per-case bisect for vitest `-t` and
  `go test -run`), 099 (pnpm and uv caches; jobs run in parallel, the longest — python — took 105 s on 2026-10-17).
- 2026-10-17: 018 (a run killed mid-fix, with half a change and a stray file, resumes from the release tag; tested),
  034 (`RunState.failures`: typed `NodeFailure` records; state schema 3 converts older `errors` pairs), 044
  (`DA_EVIDENCE_CACHE_S`: re-runs of an issue at the same release reuse its fetched telemetry; off by default, and
  D3/D4 still decide per run), 062 (`ledger.migrate` on open adds the columns an older ledger lacks and records a
  schema version; an in-house step rather than Alembic, since every change so far is an added column — a
  non-additive change gets its own step). Partly done: 093 (the quickstart now comes before the results; the
  README is not yet split into pages). 064 not started: generating the dashboard's types needs the Node toolchain,
  which hangs on this machine, so it could not be verified here.
- 2026-10-17: 020 (rider reports: an exact binomial test of how many reports had the flag against its rollout share
  feeds D11, e.g. 8 of 9 at 5%), 033 (`PlanDecision` for D12–D14 and `AttemptRecord` for validation attempts;
  `dict[str, Any]` in `pipeline/` 233 → 222, the ratchet locked there), 043 (an agent's MCP servers start together:
  6 servers in 0.48 s against 2.14 s one after another, measured here), 073 (`@debugassist …` on one of the app's
  PRs from an owner, member or collaborator reaches the diff fixer of the run that opened it), 080 (the
  `investigator` MCP server — `investigate`, `runs`, `report` — and `docs/coding-agents.md`).
- 2026-10-17: 022 (the reproduction rules moved to `pipeline/proof.py` — a first slice of 031 — with their own
  tests; `scripts/mutate.py`, a dependency-free mutation tester, and `make mutate`: 62/74 mutants killed at first,
  the survivors pointed at untested message details and a missing "raises"/"thrown" in the error-word pattern;
  after those, 74/74), 074 (a failed check on an installed repository's default branch becomes
  `GHCI:owner/repo@<id>`, run once from the poll as a draft-PR investigation).
- 2026-10-17: 046 (`debugassist app poll --workers N`: different repositories in parallel, one repository's issues in
  order; the poller's state files are written under a lock). Next up: 037, 025 (GitHub half), 093, then 031.
- 2026-10-18: 037 (`configs/deciders.yaml` routes a template to `rules`, `llm` or `mock`; a `RulesDecider` gives the
  configured fixed answers; nothing is routed by default, so behaviour is unchanged until a live arm justifies D01
  and D14 on rules), 093 (the reference sections moved to `docs/REFERENCE.md`; the README went from 44 KB to 39 KB,
  quickstart first).
