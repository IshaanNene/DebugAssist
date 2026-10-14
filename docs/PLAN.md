# DebugAssist — Plan

The design as built, and what changed from the spec on the way. Requirements: [SPEC.md](SPEC.md). Build log:
[PROGRESS.md](PROGRESS.md). What comes next: [ROADMAP.md](ROADMAP.md). The original plan of 2026-10-04, with its
amendments as they were added, is archived in [history/PLAN-2026-10-04.md](history/PLAN-2026-10-04.md).

## 0. Decisions that override the spec

The spec was written around the Claude Agent SDK. These decisions replace it where they conflict; the A-numbers are
the amendments in the archived plan, which PROGRESS and the ADRs cite.

| # | Decision | Where it lives |
|---|---|---|
| A1 | **No Anthropic or Claude SDK calls.** All LLM work — RCA, subagents, reproduction, fix, diff fixer, chat, the LLM decider — goes to an OpenAI-compatible API. The agent loop is LangChain `create_agent` + `langchain-mcp-adapters`, behind the `LLMRunner` seam. | `packages/llm`, ADR 0004 |
| A2 | "Which model" becomes **reasoning effort on one model**, chosen per node and routed by D10. | `configs/agent_types/*.yaml` |
| A3 | **Our own coding tools** (`read_file`, `outline_file`, `grep`, `edit_file`, `write_file`, `run_command`, …), scoped to the sandbox worktree and wrapped by the command, egress and secret guards. | `packages/llm/.../workspace_tools.py` |
| A4 | **Skills in the Claude Code plugin format** (`plugin.yaml` + `skills/*/SKILL.md`), loaded by progressive disclosure under a token budget. | `marketplace/` |
| A5 | **`LLMDecider`** (System One adapter, OpenAI-compatible) replaces the spec's `ClaudeDecider`, as the baseline and the "no Clef" ablation. | `packages/decisions` |
| A6 | **Tracing** with OpenInference's LangChain instrumentor, to Phoenix and optionally Langfuse (`DA_TRACING`). | `packages/core/.../tracing.py` |
| A7 | **Clef** on Cloudflare Workers AI (`clef`, `clef-flash`), envelope verified live. The token is IP-restricted and expires 2026-11-03, so CI uses the mock decider. | `packages/decisions` |
| A9 | `miniride-client` is **public**, `miniride-services` **private**. A clone skips the private submodule (`update = none`), runs every test and regenerates the evaluation report; the live stack and demos need access. | `.gitmodules`, README › Quickstart |
| A11–A13 | **Provider and model are configuration**: OpenRouter or GroqCloud (`LLM_PROVIDER`, `LLM_MODEL`); currently **OpenRouter `openai/gpt-6-luna`**, after `gpt-oss-120b` and Nemotron (free, but one overloaded host). Capabilities and prices come from `core.llm_models.model_info`. | ADR 0007, `.env` |
| — | **Chat is a Discord webhook** (or a mock inbox) instead of Slack, which needed a paid workspace. Never exercised live. | `packages/integrations/.../chat.py` |
| — | **Python 3.13**, uv workspace, shared `debugassist.*` namespace; **ground truth in `groundtruth/`**, outside the target repos and never mounted into a sandbox. | ADR 0005, `groundtruth/` |

## 1. Principles

1. **The plan is fixed in code.** A static LangGraph graph; models never choose the next step. Decisions pick among
   edges that already exist, and a policy maps each decision's probability to *act*, *escalate* or *safe default*.
2. **Decide, reason, act — kept apart.** Clef (or the LLM decider) makes typed judgement calls; LLM agents reason
   and write code inside turn and budget caps; deterministic code performs every write, through a policy gate and an
   audit log, dry-run by default.
3. **Mock mode is a first-class backend.** Every integration (LLM, Clef, GitHub, Jira, chat) has a live and a mock
   implementation, chosen per integration from `.env` (`DA_MODE_<INTEGRATION>=live|mock`, `replay` for the LLM).
   CI has no secrets and runs everything in mock mode.
4. **Ground truth never reaches the agent.** Injected bugs land as ordinary-looking commits; the catalog, patches
   and hidden tests stay in `groundtruth/`, read only by the scorer after a run.
5. **Mock results are never reported as results.** Every run and ledger row carries its mode; README and site
   numbers come only from generated reports of live runs.

## 2. The pipeline

```
ingest → auto_triage (D01, D02) → context_collector (D03, D04) → classify_rca (D05–D10)
   ├─ not actionable (D05), or the RCA's own category is not a code change in our repos ─→ ship_gate
   └─ mitigate (D11) ─ the flag itself is the defect and a rollback was decided ─→ ship_gate
        └─ fix (D12, D13) → validate (D14) ─ retry, at most 3 attempts (D15) ─→ fix
                 └─ ship_gate (D16) → pr_and_notify → post_merge_watch (D17)
```

- **18 decision templates** (D01–D18, D18 for developer feedback), each with a policy band and a ledger row.
- **11 MCP servers** are the only way agents see the world: crash analytics, bug reports, code search, git
  history, releases, logs, tracing, metrics and profiles, feature flags, incidents, Jira ([mcp.md](mcp.md)).
- **Evidence ids** are content hashes; every RCA claim cites them, and D09 checks each claim against its evidence.
- **Cross-repo hand-off**: when the root cause is in another target repo, the fix moves there (its sandbox, test
  ladder and CI).
- **Sandbox**: a network-less Docker container on a git worktree; pushes happen outside it, to `debugassist/*`
  branches of the two target repos only.

Components, stand-ins and the target system are described in [ARCHITECTURE.md](ARCHITECTURE.md); decisions in
[decisions.md](decisions.md); design records in [adr/](adr/).

## 3. Repository layout

```
packages/      core · decisions · llm · pipeline · harness · integrations · mcp_servers · scenarios ·
               simulator · evals · api · cli            (uv workspace members, namespace debugassist.*)
apps/          dashboard (Next.js) · site (public site, GitHub Pages)
configs/       agent_types/ (web-crash, backend-error, perf-regression, user-bug-report) · policies/ ·
               catalog.yaml · subagents.yaml
marketplace/   plugins/ (5 skill plugins) · domains/
sources/       bugdrop · vitals · incidents          (local stand-ins for the internal tools)
targets/       miniride-client (public) · miniride-services (private)   (git submodules)
groundtruth/   bugs/ patches/ fixes/ hidden_tests/   (the answer key; never mounted into a sandbox)
evals/         runs/ · reports/ · notes/ · ledger/   (every published number is built from here)
infra/         docker-compose.yml (profiles) · otel-collector · prometheus · unleash · toxiproxy · runtime
docs/          SPEC · PLAN · PROGRESS · ROADMAP · LESSONS · ARCHITECTURE · mcp · decisions · adr/ · history/
```

## 4. Phases and status

Details, verification and caveats per phase are in [PROGRESS.md](PROGRESS.md); later work in
[ROADMAP.md](ROADMAP.md).

| Phase | Scope | Status |
|---|---|---|
| P0 | Scaffold: uv workspace, ruff, pyright strict, pytest, pre-commit, CI, compose profiles | done 2026-10-04 |
| P1 | Decision engine: Clef / Clef-flash / LLM / mock deciders, policy bands, ledger | done 2026-10-04 |
| P2a | MiniRide (React client, Node gateway, Python dispatch, Go payments), OTel, Loki, Prometheus, Unleash, Toxiproxy | done 2026-10-04 |
| P2b | BugDrop, Vitals, incidents, bug catalog, injection tooling, traffic simulator | done 2026-10-04 |
| P3 | Walking skeleton: one bug end to end, sandbox, first MCP servers, minimal guardrails | done 2026-10-05 |
| P4 | All 11 MCP servers | done 2026-10-05 |
| P5 | Triage and context collector (D01–D04) | done 2026-10-05 |
| P6 | Root cause (D05–D10): subagents, grounding, effort routing | done 2026-10-05 |
| P7 | Mitigation, fix, validation (D11–D15) | done 2026-10-05 (one acceptance item partly met) |
| P8 | Ship gate, PR, Jira, chat, post-merge watch (D16–D17) | done 2026-10-05 |
| P9 | Dashboard | done 2026-10-05 |
| P10 | Post-PR features and feedback (D18) | done 2026-10-05 |
| P11 | Harness: agent types, skill marketplace, PEX packaging, runtime images, workers | done 2026-10-05 |
| P12 | Observability, cost, guardrails, privacy | done 2026-10-05 |
| P13 | Evaluation harness, catalog of 25 bugs with hidden tests, ablations, reports | done 2026-10-07 |
| P14 | Cross-repo investigation and hand-off | done 2026-10-10 |
| P15 | Context engineering (lean reads, clearing, compaction, concise results) | measured, kept opt-in |
| P16 | Langfuse | done 2026-10-10 |
| P17 | Public site | done 2026-10-10, kept current |
| — | Three-seed full run; fix round; Clef vs no-Clef ablation | done 2026-10-11 → 14 |
| P18 | Evaluation at scale; prove or rework Clef; a real open-source bug | open |

## 5. Evaluation

- **Catalog**: 25 synthetic bugs injected into MiniRide (19 that need a code fix, 6 where the right answer is to
  route), each with a natural-looking injection, a trigger scenario, root-cause facts and hidden tests.
- **Scoring**: root cause *exact* (file and function) or *directional* (file or module); category; outcome; fix
  validated; hidden tests on the fix. Infrastructure faults are excluded with a reason, never counted.
- **Arms**: the main configuration with three seeds per bug, re-runs after each round of fixes, context-engineering
  arms, and a `no-clef` arm in which the LLM makes every Clef decision. The decision replay (E1) re-decides every
  logged decision with Clef, Clef-flash, the LLM decider and rules.
- **Reports** are generated by `debugassist eval report` from `evals/runs/` and `evals/ledger/`, and reproduce
  from a plain clone. Current numbers and caveats: README › Results and Limitations, and the latest report.

## 6. Cost

Measured, not estimated: a median of about **$0.015 per end-to-end run** on `openai/gpt-6-luna` (prompt caching
does most of the work), and **under $2** for a full three-seed sweep of the catalog. Every sweep is priced first
(`debugassist eval estimate`), stops before the key runs dry (`--reserve-usd`), and anything estimated above **$5**
is asked for first. The spec's original cost model (Claude prices, about $2.50–6 a run) is in the archived plan.

## 7. Risks, as they stand

| Risk | Status |
|---|---|
| Ground-truth leakage inflating results | Isolation test; natural-commit injection; scorer reads ground truth after the run. The answer key is in a public repo, so a future model could be trained on it — stated in README › Limitations. |
| Synthetic bugs written by the same author as the skills | Open. Skills are generic and linted for leaks; a real open-source bug is on the roadmap. |
| Small samples | Three seeds per bug in the headline; seeds still disagree on ten bugs. |
| Clef's value unproven | Open. The replay and the live `no-clef` arm show no clear gain; rework D01, D13, D14 first ([ROADMAP](ROADMAP.md)). |
| Clef token expiry (2026-11-03) | Mock decider in CI; live Clef needs a renewed token. |
| Reproducibility | A clone runs every test and the full report; the live stack needs the private services repo. |
| Prompt injection via reports, logs, code | Untrusted-data fencing, read-only tools by default, write policy gate, injection fixtures (P12). |
| Writes reaching real systems | Push allowlist of the two demo repos, `debugassist/*` branches only, dry-run default, audit log. |
