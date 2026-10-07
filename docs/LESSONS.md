# Lessons learned

Every problem that cost real time while building DebugAssist: what we saw, why it happened, what fixed it, and
what now stops it coming back. Most were found by a live run, not by reading code — which is the main lesson.
Phase-by-phase detail is in [PROGRESS.md](PROGRESS.md).

Format: **symptom** → cause → fix · *guard*.

## 1. LLM providers, routing and cost

- **Calls hung for minutes and never timed out.** OpenRouter keeps queued requests alive by streaming whitespace,
  so HTTP read timeouts never fire. → Every model call has a 300 s wall-clock bound plus backoff retries;
  daily-quota 429s fail fast. *Guard: `bounded_model_call` middleware.*
- **Unparseable structured output from gpt-oss.** Default routing picked hosts that padded or broke JSON. → Pin
  hosts and send `require_parameters`. *Guard: per-model provider order in settings.*
- **Every eval call hit 429 `engine_overloaded`.** `require_parameters` plus three parameters — `json_schema`,
  `seed` and LangChain's `parallel_tool_calls=false` — left Nemotron with exactly one eligible host, and it was
  overloaded. → `LLM_STRUCTURED_OUTPUTS=false` (function calling instead), no `seed` on OpenRouter, drop
  `parallel_tool_calls`. Diagnosed by calling each host directly and reading OpenRouter's routing funnel in the
  404 body. *Guard: tests for the override; PLAN A13.*
- **The LLM decider failed on the first rate limit.** The engine's retry policy totalled under a second. → 5/15/30 s
  backoff on 429/5xx inside the decider. *Guard: `RATE_LIMIT_BACKOFF_S`.*
- **"Chat completion did not complete: length".** The decider capped output at 2,000 tokens, reasoning included;
  without strict JSON mode the model reasoned longer. → Cap from settings (up to 8,000).
- **The agents could not finish on Groq's free plan.** 8K tokens/minute leaves ~5K per request: not enough to
  keep the bug, the store and an example test in view, so agents re-read files forever. → Token budget, history
  trimming and dropped-step notes keep it working, but the real fix was a paid tier. *Lesson: measure tokens per
  turn before choosing a free tier.*
- **The OpenRouter key expired mid-plan, and credit ran low mid-sweep.** → `credit_remaining()` reads the key's
  limit; `eval run --reserve-usd` stops cleanly before the next bug. *Guard: the eval refuses estimates above
  `--max-usd`.*
- **Cost estimates were 3× too low.** The per-run average came from mostly RCA-only runs; full fix-and-validate
  runs cost ~$0.50 on Nemotron. → Estimate per scope; switching to `openai/gpt-6-luna` cut a full run to ~$0.02.
- **The prompt cache never hit.** OpenRouter load-balanced one run across several hosts, and each host has its own
  cache. → OpenAI-hosted models route `openai → azure`; cached tokens are recorded per turn and priced at the
  cache-read rate. *Guard: `cached_tokens` in every agent log line.*

## 2. The agent loop and context

- **A resumed run reloaded a stale agent.** Agents built inside a pipeline node inherited the pipeline's
  checkpointer and thread. → `checkpointer=False` for agents.
- **Agents were cut off early and their transcripts lost.** The step limit assumed 3 graph steps per turn; a
  turn takes about 5. → 6 per turn + 20, and state is streamed so a failure keeps the transcript.
- **"RCA agent ended with status no_output".** The model answered in prose without calling the output tool, and
  the structured-extraction fallback then got a 404 from OpenRouter (the `parallel_tool_calls` issue above). →
  Fixed the fallback; it now turns the transcript into the result.
- **Mitigation crashed on a 404 from Unleash.** It used the RCA's free text — `notif_router_v2 (irrelevant — flag
  is off…)` — as a flag name. → Only a real flag name found in that text acts (`known_flag`). *Guard: test.*
- **True claims were rejected by grounding (D9).** Two causes: batching every claim with all cited evidence lost
  which evidence belonged to which claim (true claims scored 0.03–0.27 batched, 0.87–0.99 alone), and tool
  results were kept as 600-character previews. → One call per claim; evidence-bearing tool results keep 6,000
  characters. *Guard: `test_rca.py` checks each call sees only its own citations.*
- **The e2e agent only "submitted" at its turn cap.** It had no way to run its Playwright spec. → A `run_e2e` tool.
- **Early fixes suppressed symptoms.** Optional chaining over the crash, a test asserting the buggy behaviour, a
  test-only draft PR. → The reproduction must fail on the shipped release with the production error, and the ship
  gate requires a verified reproduction plus a source change.
- **Validated is not the same as correct.** Several fixes passed the agent's own reproduction but not the
  catalog's hidden test — the agent's test was narrower than the bug. *Guard: hidden tests in the evaluator.*
- **Backend bugs reported from the app were fixed in the wrong repo.** With only a rider's report, the agent stayed
  in the client and patched the symptom. *Open — the next work item ([ROADMAP](ROADMAP.md)).*

## 3. Decisions (Clef)

- **Clef rejected a decision.** Two-stage D12 sent `path::function` as question ids; Clef accepts only
  `[A-Za-z0-9_.-]`. → Opaque ids. *Guard: a test through the real engine.*
- **Evidence ids changed between processes.** They used Python's salted `hash()`. → `evidence_id()` (content hash).
- **D2 marked the original crash a duplicate of a report filed 1.5 hours later.** → Only issues opened *before* the
  one being triaged are candidates; the earliest is canonical.
- **The keyless demo stopped after RCA.** New decisions shifted the mock's pseudo-random answers. → The demo pins
  its decisions (still labelled mock).
- **The rules baseline beats Clef on two decisions** (triage and test tier, in the E1 replay). *Open — template work.*

## 4. Sandbox, packaging and the machine

- **Every Go sandbox command failed with `go: not found`.** Commands ran in a login shell (`sh -lc`), and Alpine's
  `/etc/profile` resets `PATH`, dropping `/usr/local/go/bin`. It hid a fully correct fix on BUG-005. → Plain
  `sh -c`.
- **A missing image after a Docker reset broke dependency install.** → Pull a missing image before the timed
  install step.
- **Validation rejected every revised fix.** The contract check reverted "the source change" with `git diff HEAD`;
  once a fix is committed, HEAD already contains it. → Diff against the release tag. A related bug reset the
  sandbox to the bot branch (the previous fix) instead of the release.
- **The PEX didn't work.** File-relative paths and `python -m` for MCP servers break inside a PEX. →
  `DEBUGASSIST_ROOT`, templates packaged into the wheel, `PEX_MODULE`.
- **iCloud Desktop.** Unreadable placeholders ("Resource deadlock avoided"), `* 2` conflict copies, and macOS
  hiding files in dot-directories so Python 3.13 skipped `.pth` files. → The PEX build copies only the Python
  workspace; `make sync` installs a path hook. *Lesson: don't keep a repo in an iCloud-synced folder.*
- **A case-insensitive collision.** A new `.debugassist/` scratch dir collided with the tracked `.DebugAssist/`. →
  `.da-e2e/`.
- **No host networking on Docker Desktop.** → Runtime containers join the compose network and use service names.
- **Long runs died when the laptop slept.** → Detached processes, the app's keep-awake hold, and evaluations that
  resume from the next bug.

## 5. Telemetry stack

- **Jaeger returned nothing.** Jaeger 2 serves only the v3 query API (streamed OTLP JSON), and health checks filled
  its "latest N traces" window. → Parse the stream; search per server-side operation.
- **Instrumentation silently did nothing.** SQLAlchemy 2.1 is skipped by its OTel instrumentation (pinned 2.0.x);
  Node ESM needs `module.register(".../hook.mjs")`; Go's `NewWithAttributes` clashed with the SDK schema
  (`NewSchemaless`).
- **Log templates didn't collapse.** `13` was masked but not `13ms` (no word boundary). → Fixed with a test.

## 6. Simulating production

- **Many catalog bugs were caught by the target repos' own CI** (a deprecated `utcnow`, a test without props,
  GraphQL coercing numeric strings). → Discarded: a bug CI catches isn't realistic. Every regression must pass lint
  and tests. *Guard: `make verify-scenarios`.*
- **Crashes never reached Vitals.** A render error inside a route is caught by react-router's error page, not the
  app's crash handler. → Simulated riders treat that page as a crash and report it.
- **Five of seventeen new bugs were never discovered.** A scenario aborted when a crash killed a booking;
  riders quoted before a flag change propagated (services poll every 5 s); concurrent bookings raced onto the same
  free driver so a market never filled; a short trip hid a wrong in-trip ETA. → Each fixed; discovery checked live.

## 7. Keeping the evaluation honest

- **The evaluator investigated a duplicate.** D2 correctly attached a rider's report to the same bug's crash
  issue, and the run stopped. → Follow the duplicate to the canonical issue.
- **A scorer bug inflated the headline from 0.64 to 0.92.** Path normalisation prefixed the component to any path,
  crediting client answers to services modules. A first fix depended on a checkout CI doesn't have. → Honour the
  repo the agent names. *Guard: tests; caught by reading the report before publishing it.*
- **"Outcome" counted runs that never reached the ship gate as failures.** → Counted only where an outcome exists.
- **Post-hoc scoring rules.** One grading rule (not-our-code with the wrong subtype = directional) was added after
  seeing runs. → Stated in the report; `eval rescore` re-applies the current scorer to every saved run.
- **Infrastructure failures counted against the agent.** → Rows can be `excluded` with a reason; the report lists
  them instead of hiding them.
- **A shell loop silently did nothing.** zsh doesn't word-split `$VAR`, so `for d in $D` ran once on one bogus
  path and an earlier rescore never applied. *Lesson: print what a batch step did.*

## 8. Process

- **An `--amend` rewrote a pushed commit** after a pre-commit hook failed the commit before it. → Soft reset to
  `origin/main` and a new commit; no force push.
- **Trying to mimic CI by moving a submodule to `/tmp`** turned into a cross-filesystem copy of the whole repo. It
  was stopped before anything was lost (`git fsck` clean). *Lesson: simulate missing inputs in code, not by moving
  directories.*

## Patterns worth keeping

1. **Run it live early.** Mocks agreed with our assumptions; live runs found the routing funnel, the PATH bug, the
   crash boundary and the scorer bug.
2. **Read your own results before publishing them.** The two most important fixes to the evaluation came from a
   number that looked too good.
3. **Make every guard a test or a check**, so the same bug can't come back silently.
4. **Count tokens and dollars per turn**, not per run; it is where the waste shows.
