# Roadmap

Where DebugAssist goes after P13. Everything here is measured the same way the first evaluation was: a switch,
an eval run on the catalog, and a report under `evals/reports/` — no feature ships on a blog post's numbers.
Problems already solved are in [LESSONS.md](LESSONS.md).

Baseline to beat (`evals/reports/2026-10-07`, gpt-6-luna, 25 bugs, one seed): root cause right or close 16/25,
exact 12/25, code-bug fixes validated 12/19, hidden tests 7/15, median ~$0.017 per run.

## P14 · Close the biggest gap: backend bugs reported from the app — done (2026-10-10)

**Result** ([evals/reports/2026-10-10](../evals/reports/2026-10-10/report.md), the six bugs re-run): root cause right or close 0/6 → 5/6, hidden tests passing 0 → 2, fixes now made in the service. Still open: fixes after a hand-off that don't validate (3 of 5), and CORS (BUG-017), which is invisible from the client. **Fix quality** (commit `85cb379`): a Python sandbox interpreter fix, the eval retry loop and a forgiving edit tool took hidden-test passes on eight re-run bugs from 0 to 5. Not yet done from the list below: contract evidence (GraphQL schema / API shapes) and linked PRs when both sides change.

All six services bugs that reached us only through a rider's report were investigated in the client repo.

- Give `user-bug-report` both repos (client + services) and the gateway/dispatch/payments MCP evidence.
- A cross-repo hand-off: when the RCA's location is in another repo, re-plan the fix there (new sandbox, that
  repo's ladder and CI), and link both PRs if both sides change.
- Contract evidence for the agent: the GraphQL schema and service API shapes, so field-name drift is visible.
- **Measure:** BUG-013/014/015/017/019/020 root cause and hidden tests; no regressions on the other 19.

## P15 · Context engineering (how Claude Code does it, applied here)

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
opt-in switch. Next: item 3 (clear old results) and item 7 (compaction with notes), because the history re-sent on
every turn is what grows — and repeated seeds before trusting any small difference.

**Clearing arm result** (`DA_CONTEXT=clear`, item 3: tool results older than the newest three become one-line
stubs — tool, arguments, size, evidence id — in batches triggered at 4K tokens, so the prefix only changes once per
batch; same eight bugs, *Context by arm*): input per turn and per run fell, but the cache hit rate fell with it, so
cost moved by a few percent. Root cause right or close matched; hidden-test passes were lower, within one-seed
noise. Kept opt-in. Next: item 7 (compaction with notes), which keeps a digest instead of stubs.

**Compaction arm result** (`DA_CONTEXT=compact`, item 7: steps older than the newest two fold into structured notes
written by the same model once they pass 4K tokens; **partial — three of the eight bugs** before the API credit ran
out): input per turn matched the baseline (the notes and their model calls cost what they removed); one run's climb
through three reproduction tiers doubled the total. Inconclusive; kept opt-in. Next: item 4 (concise tool
responses), then repeated seeds for everything before trusting small differences.

**Concise responses, estimated offline** (`DA_CONTEXT=concise`, item 4: compact JSON instead of two-space-indented,
lists cut to the top 10 with a count of the rest, long fields clipped, grep output to 30 lines; built, not yet run
live — the API credit ran out): replaying the fix-quality arm's transcripts through it removes about 5% of the
re-sent history, roughly 2–3% of the arm's input, because `read_file` (untouched) dominates and MCP results are
already capped. Deterministic, so the cache prefix is unaffected. A small lever; run it live when there is credit.

## P16 · Integrations (free / open source)

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

## P17 · A public site

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
- Lessons learned and roadmap pages generated from these docs.

## P18 · Evaluation at scale

- Three seeds on the main arm; Clef vs Clef-flash vs LLM decider vs rules as full pipeline arms; skills-off.
- Decision templates where the rules baseline wins (triage, test tier).
- Grow the catalog: concurrency bugs, data migrations, memory leaks, third-party API changes, security fixes.
- The external benchmark arm (SWE-bench subset) and a baseline agent (P16).

## Later

- **DebugAssist as a tool for coding agents**: an MCP server and a `SKILL.md` so Claude Code, Cursor or Codex can
  ask it "investigate VIT-1001" and get the RCA and proof back.
- A GitHub App instead of a token; a Helm chart; multi-tenant runs.
