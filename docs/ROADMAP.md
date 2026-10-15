# Roadmap

Where DebugAssist goes after P13. Everything here is measured the same way the first evaluation was: a switch,
an eval run on the catalog, and a report under `evals/reports/` — no feature ships on a blog post's numbers.
Problems already solved are in [LESSONS.md](LESSONS.md).

Baseline to beat (`evals/reports/2026-10-15`, gpt-6-luna, 25 bugs, each bug's latest three-seed run — 17 on
`d7cf020`, 8 re-run on `becdbde` after the fix round; 75 runs): root cause right or close 80%, exact 65%, category
right 75%, code-bug fixes validated 81%, hidden tests 80%, median $0.014 per run. (The first one-seed run,
`evals/reports/2026-10-07`, scored 64% / 48% / 72% / 63% / 47%.)

## Parked (2026-10-14)

Built or started, measured where possible, and stopped on purpose. Parked means the code stays and is **off by
default**, nothing here is a next step, and an item comes back only with a reason (a new result, a new need).

| Item | State | Why parked |
|---|---|---|
| `DA_CONTEXT=lean` (capped reads, `outline_file`, `read_log`) | Built, measured on 8 bugs | Agents made more, smaller reads: input per run went *up* |
| `DA_CONTEXT=clear` (old tool results become stubs) | Built, measured on 8 bugs | Input per turn −17%, but the cache hit rate fell with it: cost about level |
| `DA_CONTEXT=compact` (older steps folded into notes) | Built, measured on 3 bugs | The notes cost what they removed; inconclusive and not worth a full arm |
| `DA_CONTEXT=concise` (compact JSON, top-k lists) | Built, estimated offline | About 2–3% of input by replay: too small to spend a live arm on |
| P15 items 5, 6, 9, 10 (tool-use examples, programmatic tool calling, per-repo memory, tool search) | Not started | The audit puts the weight in re-sent `read_file` results, which none of these address |
| Discord chat notifier | Built, tested against a mock transport | Never run against a real webhook (no workspace); pages go to the mock inbox |
| P16 integrations other than Langfuse (LiteLLM, local models, Promptfoo, Inspect, GlitchTip, OpenFeature, ast-grep, SWE-bench, OpenHands, Temporal) | Ideas, not started | Kept as a list; the open evaluation questions come first |

## P14 · Close the biggest gap: backend bugs reported from the app — done (2026-10-10)

**Result** ([evals/reports/2026-10-10](../evals/reports/2026-10-10/report.md), the six bugs re-run): root cause right or close 0/6 → 5/6, hidden tests passing 0 → 2, fixes now made in the service. Still open: fixes after a hand-off that don't validate (3 of 5), and CORS (BUG-017), which is invisible from the client. **Fix quality** (commit `85cb379`): a Python sandbox interpreter fix, the eval retry loop and a forgiving edit tool took hidden-test passes on eight re-run bugs from 0 to 5. Not yet done from the list below: contract evidence (GraphQL schema / API shapes) and linked PRs when both sides change.

All six services bugs that reached us only through a rider's report were investigated in the client repo.

- Give `user-bug-report` both repos (client + services) and the gateway/dispatch/payments MCP evidence.
- A cross-repo hand-off: when the RCA's location is in another repo, re-plan the fix there (new sandbox, that
  repo's ladder and CI), and link both PRs if both sides change.
- Contract evidence for the agent: the GraphQL schema and service API shapes, so field-name drift is visible.
- **Measure:** BUG-013/014/015/017/019/020 root cause and hidden tests; no regressions on the other 19.

## P15 · Context engineering (how Claude Code does it, applied here) — measured, parked

Every turn re-sends the system prompt, tool schemas and the whole history; on BUG-001 a full run read ~300K input
tokens. Tool schemas are only ~2–2.5K tokens per agent — the weight is tool *results* re-sent every turn. Ordered
by expected value; each item is a switch in `core/ablation.py` and an eval arm.

| # | Technique | What it means for us | Where it comes from |
|---|---|---|---|
| 1 | **Prompt anatomy audit** | Dump exactly what each node sends per turn (system / skills / tools / history / tool results, in tokens), and keep the stable parts first and identical across turns so the cache hits | Claude Code keeps its system prompt stable and appends dynamic context late |
| 2 | **Tool-result offloading** | Large tool results go to a file in the run dir; the model gets a short summary plus a handle, and reads ranges on demand | Claude Code saves big outputs to disk and passes a path; "just-in-time" retrieval |
| 3 | **Tool-result clearing** | Once a step is done, older raw tool outputs in history are replaced by a one-line stub (append-only, so the cache prefix survives) | Anthropic context-editing / tool clearing |
| 4 | **Concise response formats** | Tools take `detail="concise" \| "full"`; default concise (ids, counts, top-k) | Anthropic, *Writing effective tools for agents* (~⅓ the tokens) |
| 5 | **Tool-use examples** | Two or three worked calls in the descriptions of the tools agents misuse (pick them from bad-argument / unknown-tool errors in the eval logs) | Anthropic advanced tool use (reported 72% → 90% on complex parameters) |
| 6 | **Programmatic tool calling** | A `run_tool_script` tool: the agent writes a short Python script in the sandbox that calls MCP tools, filters results, and prints a summary — fan-out without each result entering context | Anthropic PTC (−37% tokens on research tasks; but ~+8% cost on sequential single-call work — measure, don't assume) |
| 7 | **Compaction with notes** | Long agents keep a structured notes file (hypotheses, evidence ids, ruled out) and compact history into it near a budget | Claude Code compaction; structured note-taking |
| 8 | **Repo map instead of file reads** | A tree-sitter / ast-grep symbol map of the repo for localisation; read files only at the chosen spot | Aider-style repo maps |
| 9 | **Per-repo memory** | A small `DEBUGASSIST.md` per target repo (conventions, flaky tests, where things live) grown from accepted PR reviews (D18) | `CLAUDE.md` / project memory |
| 10 | **Tool search** | Only once an agent has >~30 tools: list names, load schemas on demand. On OpenAI-hosted models the tool list is part of the cached prefix, so loading tools mid-run costs cache hits | Claude Code deferred tools; Anthropic Tool Search Tool |

- **Measure per item:** input tokens per run, cache-hit rate, cost, turns, and RCA/hidden-test results vs baseline,
  on the same bugs. Report the table, keep what helps.

**Audit result** (`debugassist eval context`, [evals/reports/2026-10-07/context.md](../evals/reports/2026-10-07/context.md),
25 runs, 7.5M input tokens): 53% are tool results re-sent on later turns — `read_file` alone 32% (each read re-sent
~7×) — 35% is the fixed prefix (the RCA task with its evidence bundle is ~7.9K tokens a turn), 12% the model's own
messages. **82% of input is already served from the prompt cache**, because history is append-only. So:
*adding less* (targeted reads, a repo map, concise responses — items 2, 4, 8) cuts tokens and cost; *clearing*
old results (item 3) rewrites the cached prefix and may cost more than it saves — measure it last.

**Lean arm result** (`DA_CONTEXT=lean`, items 2/4/8 in part: reads capped at 120 lines with an `outline_file` tool,
long command logs behind `read_log`; eight bugs, one seed, [report 2026-10-10](../evals/reports/2026-10-10/report.md),
*Context by arm*): **no saving.** Agents made more, smaller reads, so input per run rose and `read_file`'s share
went up; cost stayed about level on a higher cache rate, and outcomes were within one-seed noise. Kept as an
opt-in switch; followed by items 3 and 7.

**Clearing arm result** (`DA_CONTEXT=clear`, item 3: tool results older than the newest three become one-line
stubs — tool, arguments, size, evidence id — in batches triggered at 4K tokens, so the prefix only changes once per
batch; same eight bugs, *Context by arm*): input per turn and per run fell, but the cache hit rate fell with it, so
cost moved by a few percent. Root cause right or close matched; hidden-test passes were lower, within one-seed
noise. Kept opt-in; followed by item 7.

**Compaction arm result** (`DA_CONTEXT=compact`, item 7: steps older than the newest two fold into structured notes
written by the same model once they pass 4K tokens; **partial — three of the eight bugs** before the API credit ran
out): input per turn matched the baseline (the notes and their model calls cost what they removed); one run's climb
through three reproduction tiers doubled the total. Inconclusive; kept opt-in; followed by item 4.

**Concise responses, estimated offline** (`DA_CONTEXT=concise`, item 4: compact JSON instead of two-space-indented,
lists cut to the top 10 with a count of the rest, long fields clipped, grep output to 30 lines; built, not yet run
live — the API credit ran out): replaying the fix-quality arm's transcripts through it removes about 5% of the
re-sent history, roughly 2–3% of the arm's input, because `read_file` (untouched) dominates and MCP results are
already capped. Deterministic, so the cache prefix is unaffected. A small lever; parked without a live run (see Parked).

**Repeated seeds — done (2026-10-11).** `make eval-full` ran every catalog bug three times on commit `d7cf020`
(arm `full-d7cf020`, 74 counted runs, under $2); it is now the headline of the README card, the site and the report.
Seeds disagree on at least one lane for 8 of 25 bugs. What it found, and the fix round that followed, are under "Fix round after the full run".

## Fix round after the full run — done (2026-10-11), tuning stopped

Every remaining miss was read run by run; each is a pattern with a generic fix (no catalog hints), measured as its
own arm on the affected bugs plus a few that pass today. Rules (`9c3114e`) and routing (`becdbde`):
- RCA prompt: cover every behaviour the regression commit changed (BUG-003); fix the condition, not the reported
  input (BUG-009); our services are own code (BUG-013 seed 2, a regression from the vendored-code rule); an active
  incident with no correlating change is infra (BUG-006); check that an endpoint served other requests before
  blaming its address (BUG-017); follow a failed outbound call to the service it called (BUG-018); read the code
  before submitting a mechanism, or D13 escalates (BUG-020); a release correlates only if failures follow it across
  devices (BUG-022).
- Routing: route on the RCA's own category, not only Clef's pre-RCA D05 decision — seven runs named the right
  not-our-code category and still attempted code fixes (BUG-021/024/025); let the flag-rollback step act on rider
  reports, which have no crash fingerprint (BUG-024).

**Measured (`fixes-becdbde`, 2026-10-11), then stopped.** The prompt rules and the routing fix were re-run on eight of
the targeted bugs (three seeds) plus four regression checks (all still pass). Wins: BUG-022 wrong ×3 → exact ×3,
BUG-025 and BUG-024 from code fixes that shouldn't exist to exact (3/3, 2/3), at about a cent a run instead of five
to ten; hidden tests on BUG-003 0/3 → 2/3 and BUG-009 1/3 → 2/2. No change on BUG-006; BUG-013 worse (wrong ×3);
BUG-021 now `infra` instead of `network` (still routed). Each further rule moved bugs both ways, so prompt tuning
stopped here. Not done: BUG-017/018/020 with the new code; giving D05 the active incidents (the RCA saw BUG-006's
incident and still blamed code — a pre-RCA routing signal is the likelier fix).

## P16 · Integrations (free / open source) — Langfuse done; the rest are ideas, parked

| Tool | License* | Why here | Plan |
|---|---|---|---|
| **Langfuse** ✅ | MIT (core) | Open LLM observability + datasets + experiments + scores; self-hosts on Postgres, Redis, MinIO (we already run them) + ClickHouse | **Done (2026-10-10):** `make langfuse` self-hosts v4 on :3200 (ClickHouse added, the rest shared); `DA_TRACING=phoenix\|langfuse\|both` exports the same OpenInference spans to its OTLP endpoint; `debugassist eval langfuse --runs …` sends each sweep as a Langfuse *experiment* (v4 replaced dataset runs) with one item per bug and scores for root cause, category, validation, hidden tests, cost and turns; the dashboard links a run's Langfuse trace. |
| **LiteLLM** (proxy) | MIT | One gateway for every provider: fallbacks, budgets, caching, cost logs | Optional `LLM_PROVIDER=litellm`; per-run virtual keys as a second budget guard |
| **Ollama / vLLM** | MIT / Apache-2.0 | Free local models for development and a no-cost eval arm | `LLM_PROVIDER=ollama`; a "local" arm in the report |
| **Promptfoo** | MIT | Regression tests for prompts and skills in CI | Golden RCA/fix prompts from the catalog; fail CI on regressions |
| **Inspect AI** | MIT | A standard eval framework; makes the catalog runnable by others | Export the catalog as an Inspect task |
| **GlitchTip** (Sentry-compatible) | MIT | Real crash-report format instead of only our Vitals stand-in | A `glitchtip` source + MCP server; the client SDK can report to both |
| **OpenFeature** (+ flagd) | Apache-2.0 | Vendor-neutral flags | Feature-flags MCP behind the OpenFeature API; Unleash stays the default |
| **ast-grep / tree-sitter / Semgrep CE** | MIT / MIT / LGPL-2.1 | Structural code search, repo maps, rule checks on fixes | Code-search MCP tools; a pre-PR rule check |
| **SWE-bench Lite / Verified** | MIT | External validity beyond our own catalog | A subset run through reproduce → fix → validate |
| **OpenHands / mini-SWE-agent** | MIT | Baselines: what does a general coding agent score on our catalog? | Same bugs, same budget, compared in the report |
| **Temporal** | MIT | Durable runs that survive restarts and sleep | Optional executor for long runs (LangGraph checkpoints already resume) |

\* Check each license at adoption. Note: Arize Phoenix (our current tracer) is Elastic License 2.0, not OSI open
source — one more reason to support Langfuse.

## P17 · A public site — done (2026-10-10), kept current

A marketing site in `apps/site`, statically built and deployed from GitHub Actions to GitHub Pages (free; Vercel
works too). Our own name and content; visual language inspired by modern OSS developer sites: off-white grid
paper, a highlighter accent, monospace labels, isometric line diagrams.

- Hero: what it does in one line, the results card, Quickstart and GitHub buttons.
- The loop, drawn isometrically: crash → triage → root cause → mitigate → reproduce → fix → validate → PR → watch,
  with the Clef decision points; hovering a stage shows what runs there.
- Feature cards: evidence-backed RCA, proof before PR, Clef decisions, sandbox and policy gate, dashboard, harness.
- Results: built from the latest `evals/reports/*/results.csv` at build time (no hand-entered numbers), with the
  honest "what doesn't work yet".
- "Works with your stack": MCP servers, providers, frameworks, telemetry.
- Lessons learned and roadmap pages generated from these docs. *(Not done yet.)*

**Status.** Live on GitHub Pages, redeployed by every push that touches the site or its data. Done: hero with a
replayed real run, the isometric pipeline (the current phase opens into its steps, coloured by code / LLM / Clef)
and architecture diagrams (hover explains each layer), feature cards, results built from the latest report (each
bug's latest three-seed run; misses in neutral grey, never red; re-run panels before → after), the context-arm
token comparison, Quickstart.

## P18 · Evaluation at scale

- Three seeds on every arm (the main arm has them since 2026-10-11); Clef vs Clef-flash vs LLM decider vs rules as full pipeline arms; skills-off.
- **Prove or rework Clef.** The replay shows no accuracy gain over an LLM decider, and the live `no-clef` arm
  (2026-10-14, 24 bugs, one seed) a small edge for Clef within noise; rules win on D01 triage and D14 test tier, and
  D13 escalated BUG-020 to a human in every Clef seed. Rework D01, D13 and D14 first, then re-measure with three
  seeds on both arms.
- Routing on the RCA's category made a wrong "not ours" RCA terminal (BUG-011 in the `no-clef` arm): route away
  only when the RCA's category agrees with D05 or carries high confidence.
- Open from the fix round: give D05 the active incidents (BUG-006); re-run BUG-017/018/020 on the new code; D11
  abstains on rollbacks for rider reports (it was calibrated on crash rates) — teach it the report case.
- **Real open-source bugs — five done (2026-10-14/15).** Five public issues from four Python libraries
  (`debugassist eval real`, groundtruth/real/REAL-001..005): root cause exact 15/15, fix validated 14/15, upstream's
  regression test 11/15. Next: other languages (TypeScript, Go), larger repos, bugs without a reproducer in the
  report; Clef once its token works from this machine again; a team catalog for real repos (triage currently assigns
  a MiniRide team).
  Adding a case: a recent issue (after the model's likely training data) on a small, offline-testable repo; a fix
  with its own regression test; the report read as the agent sees it and any sentence naming the cause or fix
  withheld and listed; the hidden test run on the buggy commit (fails) and with the upstream fix (passes), and
  checked against the issue's own expectation (adapted and documented if upstream's is stricter); the checkout
  verified with the fix — and, for a merged PR, its branch head — unreachable.
- **Fix width is the weak lane, on real code too.** Diagnosis was exact on every real-bug run; the misses were fixes
  as narrow as the report (cachetools#435 0/3), as in the catalog (BUG-003, BUG-009). A generic lever to measure: the
  reproduction step tests the behaviour's other ordinary forms (keyword arguments, sibling inputs, the same call
  through another path), not only the reported one.
- Grow the catalog: concurrency bugs, data migrations, memory leaks, third-party API changes, security fixes.
- The external benchmark arm (SWE-bench subset) and a baseline agent (P16).

## Later

- **DebugAssist as a tool for coding agents**: an MCP server and a `SKILL.md` so Claude Code, Cursor or Codex can
  ask it "investigate VIT-1001" and get the RCA and proof back.
- A GitHub App instead of a token; a Helm chart; multi-tenant runs.
