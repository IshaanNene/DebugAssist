# Decisions (D1–D18)

Clef decides, the LLM reasons, deterministic code acts ([ADR 0002](adr/0002-decide-reason-act.md)). This page documents the decision engine, its templates and thresholds. Calibration results will be added after P13 evals; **all thresholds below are initial guesses, not tuned values.**

## How a decision runs

```
template (YAML, versioned)  +  state  +  params  [+ images]
        │ render: $params → options, foreach → one question per item
        │ fit_state: decisive evidence first, token budget per template
        │ prepare_images: data URLs, ≤4, ≤4 MiB / ≤16 MP each, ≤8 MiB total (auto-resize)
        ▼
backend.run(ClefRequest)   ≤64 questions per call, chunked & concurrent beyond that
        │ WorkersAIClef ──(retries: 429/5xx/timeouts, backoff + jitter)
        │      └─ circuit breaker → LLMDecider (gpt-oss-120b via system-one-adapter) or MockDecider
        ▼
policy band on the template's policy question
        act (p ≥ τ_high) · escalate (τ_low < p < τ_high) · safe_default (p ≤ τ_low)
        escalate: llm → second opinion from LLMDecider (recorded as a child ledger row)
        ▼
Decision (probabilities, chosen, p, confidence, band, action, latency, tokens, cost, mode)
        └─ decision_ledger row (state + hash, questions, answers, band, action, cost, outcome label later)
```

The decisive probability is: noul → P(yes); choice → P(chosen option); score → expected level / (levels − 1).

**Two-stage** (D12): with more than `max_direct` candidates, the engine asks one noul per candidate (chunked by 64), keeps the top-K, then asks a single choice over those plus `none`.

## Backends

| Backend | When | Cost | Notes |
|---|---|---|---|
| `WorkersAIClef` | default when `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_KEY` exist | Clef $0.24/M in, Clef-flash $0.09/M in | REST, envelope unwrapped; 4xx not retried (recorded error fixtures) |
| `LLMDecider` | baseline (`--backend llm`), breaker fallback, escalation second opinion | gpt-oss-120b token prices | `system-one-adapter`, verbalised probabilities; text-only (drops images, says so in `note`) |
| `LocalClef` | optional, CUDA GPU | — | Cloudflare's `joint_schema_model.py` from HF; contract only on this machine |
| `MockDecider` | no keys / CI / scripted demos | 0 | deterministic per (model, state, question); `overrides` pin answers; ledger mode `mock` |

OpenRouter routing: gpt-oss-120b's structured output degenerated into whitespace on some hosts under default routing (seen 2026-10-04). Calls now set `provider.order` (default `groq, cerebras, crusoe, deepinfra`, configurable via `OPENROUTER_PROVIDER_ORDER`), `require_parameters: true`, `reasoning.effort: low` and a `max_tokens` cap. All four pinned hosts returned valid JSON in 3/3 trials.

## Templates

| ID | Stage | Questions (type) | Model | Policy question → act / escalate / safe default | τ_high / τ_low |
|---|---|---|---|---|---|
| D01_triage | auto_triage | priority, severity (score); owning_team (choice, `$teams`); customer_impacting, worth_agent_run (noul) | clef | worth_agent_run → run_agent / human / triage_only | 0.60 / 0.25 |
| D02_dedup | auto_triage | duplicate_of (choice, `$candidates` + none) | clef | none→new_issue, *→mark_duplicate / human / new_issue | 0.80 / 0.40 |
| D03_log_relevance | context_collector | relevance (score, foreach windows) | clef-flash | per item: keep / keep_if_budget / drop | 0.60 / 0.30 |
| D04_screenshots | context_collector | blank_screen, error_dialog, abnormal_battery (noul); screen (choice) + images | clef | abnormal_battery → flag_battery_evidence / keep_for_rca / none | 0.70 / 0.30 |
| D05_categorize | classify_rca | category (choice, 7); needs_code_change (noul) | clef | category → investigate or route/close RCA / **llm** / investigate | 0.70 / 0.35 |
| D06_more_evidence | classify_rca | need_more (noul); next_source (choice, `$sources`) | clef-flash | need_more → fetch_more / fetch_more / proceed | 0.60 / 0.30 |
| D07_fanout | classify_rca | spawn (noul, foreach subagents) | clef-flash | per item: spawn / spawn_if_budget / skip | 0.55 / 0.25 |
| D08_rabbit_hole | classify_rca | progressing, looping, off_goal (noul) | clef-flash | looping → stop_early / warn / continue (hard max_turns stays) | 0.75 / 0.40 |
| D09_grounding | classify_rca | supported (noul, foreach claims) | clef | per item: keep / flag_unverified / drop | 0.70 / 0.35 |
| D10_model_routing | classify_rca | difficulty (choice: small/standard/hard) | clef-flash | → effort_low/medium/high / effort_high / effort_medium | 0.60 / 0.30 |
| D11_mitigation | mitigate | rollback_flag (noul) | clef | rollback_flag / human / no_rollback — plus stats significance + policy gate | 0.85 / 0.30 |
| D12_localization | fix | is_location (noul, foreach); location (choice) — two-stage | clef | focus_location or search_wider / give_top_k / search_wider | 0.60 / 0.25 |
| D13_fix_strategy | fix | strategy (choice, 8) | clef | apply_strategy, skip_fix, escalate_to_owner / let_agent_choose / let_agent_choose | 0.60 / 0.30 |
| D14_validation_tier | validate | tier (choice: unit/integration/e2e_env/cannot_repro) | clef-flash | tier_* / climb_ladder / climb_ladder | 0.55 / 0.25 |
| D15_retry | validate | retry_succeeds (noul) — inside the fixed 3-attempt cap | clef-flash | retry / retry / stop | 0.50 / 0.20 |
| D16_ship_gate | ship_gate | outcome (choice); risk (score) | clef | open_pr, draft_pr, rca_only, escalate / draft_pr / rca_only | 0.60 / 0.30 |
| D17_post_merge | post_merge_watch | resolved (noul) | clef | close_issue / keep_watching / reopen_issue | 0.80 / 0.30 |
| D18_feedback | feedback | kind (choice, 6) | clef-flash | label_store, skill_update, human / human / human | 0.60 / 0.30 |

## CLI

```bash
uv run debugassist modes                       # which integrations are live vs mock
uv run debugassist templates [D05]             # list templates or show one
uv run debugassist decide D05 --state '{"error": "..."}'                     # auto backend
uv run debugassist decide D05 --state state.json --backend llm               # LLM baseline
uv run debugassist decide D05 --state state.json --model clef-flash --json   # force model, JSON out
uv run debugassist decide D07 --state s.json --params '{"subagents":[{"id":"perf-profiler","description":"..."}]}'
uv run debugassist decide D04 --state s.json --image screenshot.png --image battery.png
```

## Calibration

Not yet measured. Metrics per D# (accuracy / macro-F1, Brier, ECE, reliability diagram, coverage curve, latency p50/p95, $/1k decisions) arrive with the eval harness (P13); recalibration (temperature or isotonic) is enabled only if held-out ECE improves.
