# Reference

The parts of the README a first read can skip: how agents are packaged, what every MCP server offers, which models
run, where things live, and what it is built with.

## 🧰 Agent harness

- **Agent types** — `web-crash`, `backend-error`, `perf-regression`, `user-bug-report`: per-node limits, MCP servers, skills, preferred subagents and validation ladder, resolved from the issue.
- **Marketplace** — five plugins (`pr-authoring`, `test-planning`, `web-client-fixes`, `backend-fixes`, `perf-and-battery`) fetched at a pinned ref; skills are listed by name and loaded on demand within a token budget; `make lint-skills` keeps them generic.
- **Domains** — rider, dispatch, payments and platform knowledge bases with owners, loadable as `kb/<domain>/<doc>`.
- **Packaging** — each agent type builds into a PEX stored in MinIO and a runtime image; runs can be queued to Arq workers.
- **Observability** — every run is one trace (OpenInference spans for agents, tools and Clef decisions) in Phoenix, Langfuse or both (`DA_TRACING`; `make langfuse` self-hosts Langfuse); eval sweeps go to Langfuse as experiments with per-bug scores (`debugassist eval langfuse`); prompt-cache hits and cost are recorded per agent turn; a global run budget stops runaway spend.

## 🔌 MCP servers

Eleven [Model Context Protocol](https://modelcontextprotocol.io) servers with 55 tools (FastMCP over stdio) are the only way agents see production. Each agent type gets the subset it needs; the deterministic context collector calls the same functions directly. Every result carries a stable **evidence id** that RCA claims must cite, is **PII-redacted** before it leaves the server, and is **paginated and capped** (12K chars by default) so one tool call can't flood the context; logs are collapsed into templates and traces summarised. They also work from any MCP client through the committed [`.mcp.json`](../.mcp.json).

| Server | Backed by | Tools | Used by |
|---|---|---|---|
| **crash-analytics** | Vitals | `list_issues` `get_issue` `get_crash_group` `get_session` `distribution` `flag_exposure` `crash_rate_timeseries` `releases` | all agent types |
| **code-search** | the target repos | `list_repos` `search_code` `read_file` `find_symbol` `find_references` `blame` `codeowners_for` | all agent types |
| **git-history** | git | `list_tags` `previous_release` `commits_between` `commit_details` `diff_stats` `bisect_candidates` | all agent types |
| **feature-flags** | Unleash | `list_flags` `get_flag` `rollout_history` `flag_crash_correlation` `rollback_flag` | web-crash |
| **bug-reports** | BugDrop | `list_reports` `get_report` `get_logs` `get_screenshots` `get_screenshot_image` `get_ui_state_timeline` | user-bug-report, perf-regression |
| **logging** | Loki | `query_logs` `log_stats` `log_patterns` | backend-error, user-bug-report |
| **tracing** | Jaeger (OTLP) | `find_traces` `get_trace` `service_dependencies` | backend-error, user-bug-report |
| **metrics-profiles** | Prometheus + client perf samples | `promql` `service_profile` `session_perf` | perf-regression, user-bug-report |
| **incidents** | incident service | `list_active_incidents` `incident_details` `dependency_status` | backend-error, context collector |
| **releases** | Vitals sessions + git tags + Unleash | `list_releases` `version_adoption` `release_diff` `rollout_status` `last_good_and_first_bad` | context collector |
| **jira** | Jira Cloud (or mock) | `get_issue` `find_open_issue` `create_issue` `add_comment` `link_pr` `transition` | pipeline nodes only, never agents |

The one write tool an agent can reach, `rollback_flag`, asks the policy gate first ([`writes.yaml`](../configs/policies/writes.yaml) says *approval*), so from an agent it is always a dry run, and it is audited either way. Ticket writes happen only in deterministic pipeline steps. Tool reference: [docs/mcp.md](../docs/mcp.md).

## 🧠 LLM providers

Agents and the LLM decider use any OpenAI-compatible API; two providers are integrated and tested live.

| Provider | Model | Notes |
|---|---|---|
| **OpenRouter** | `openai/gpt-6-luna` (current) | Tools, strict structured outputs and `seed` on every host. OpenAI-hosted models route to one host so prompt caches hit; cache reads are priced. |
| **GroqCloud** | `openai/gpt-oss-120b` | Free plan works: requests are held under its tokens-per-minute limit by a token budget and history trimming. |

`LLM_PROVIDER` / `LLM_MODEL` pick them; capabilities and prices are read per model, so the pipeline adapts: native JSON schema or function calling, reasoning effort only where supported, and `LLM_STRUCTURED_OUTPUTS=false` for models whose structured-output hosts are scarce. Decisions themselves come from **Cloudflare Clef** on Workers AI. See [ADR 0007](../docs/adr/0007-llm-providers.md) and [PLAN A11–A13](../docs/PLAN.md).

## 🗂️ Repository map

| Path | |
|---|---|
| [`packages/pipeline`](../packages/pipeline) | the LangGraph pipeline, fix planning, validation ladder, Playwright e2e tier, post-PR tools |
| [`packages/decisions`](../packages/decisions) | Clef engine, 18 decision templates, policy bands, ledger, fallbacks and the LLM decider |
| [`packages/llm`](../packages/llm) | agent runner (LangChain + MCP), watchdog, token budgets, cache-aware cost |
| [`packages/mcp_servers`](../packages/mcp_servers) | the 11 MCP servers |
| [`packages/harness`](../packages/harness) | agent types, marketplace, skills, domains, PEX + runtime images, workers |
| [`packages/evals`](../packages/evals) | scoring, catalog labels, decision metrics, E1 replay, reports |
| [`packages/scenarios`](../packages/scenarios) · [`packages/simulator`](../packages/simulator) | bug injection and the Playwright rider fleet |
| [`packages/api`](../packages/api) · [`apps/dashboard`](../apps/dashboard) | read API with live stream · Next.js dashboard |
| [`sources/`](../sources) | Vitals, BugDrop and the incident service (this project's stand-ins) |
| [`targets/`](../targets) | MiniRide client and services (git submodules) |
| [`groundtruth/`](../groundtruth) · [`evals/`](../evals) | the catalog's answer key · runs and reports |

## 🧱 Built with

<div align="center">
<img src="../docs/assets/stack.svg" alt="Built with Cloudflare Clef, OpenRouter, GroqCloud, LangGraph, LangChain, MCP, Pydantic, Docker, OpenTelemetry, Jaeger, Loki, Prometheus, Playwright, GitHub, Jira, Unleash, Postgres and Redis" width="100%">
</div>
