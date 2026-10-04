# 0007. LLM providers are configuration: GroqCloud and OpenRouter

- Status: accepted · Date: 2026-10-04 · Refines 0004

## Context
ADR 0004 put LLM calls behind an `LLMRunner` seam, with OpenRouter `openai/gpt-oss-120b` as the only
provider. Paid OpenRouter models need credits (the account had none), the free OpenRouter tier allows
about 50 requests a day, and GroqCloud's free plan serves `openai/gpt-oss-120b` directly. Providers
differ in request fields (OpenRouter `provider` routing and `reasoning: {effort}`; Groq top-level
`reasoning_effort`), in capabilities (structured outputs, reasoning effort) and in limits.

## Decision
- Settings resolve the provider (`LLM_PROVIDER`, else GroqCloud when `GROQ_CLOUD_API` is set, else
  OpenRouter), its endpoint and key, and a default model per provider (`LLM_MODEL` overrides).
- `core.llm_models.model_info(model, provider)` gives capabilities and prices: OpenRouter's `/models`
  catalog, and a table from GroqCloud's docs. The chat factory, the agent runner and the LLM decider
  read it to choose structured-output method, reasoning effort and provider-specific fields.
- A per-request token budget (`LLM_MAX_REQUEST_TOKENS`; 5000 by default on GroqCloud, whose free plan
  allows 8K tokens per minute and counts part of `max_completion_tokens` toward it, so output is capped
  at 2500 there via `LLM_MAX_OUTPUT_TOKENS`) is enforced by agent middleware: the task stays, older tool output is
  clipped, then the oldest whole steps are dropped. The agent's state is not changed.
- Daily quotas (OpenRouter free models, Groq TPD/RPD) fail fast; per-minute limits, overloads and
  timeouts retry with backoff.

## Consequences
Switching provider or model is an environment change. On Groq's free plan a run is slower (roughly one
full-size call per minute) and the agents see less history per call. Adding another
OpenAI-compatible provider means a settings entry, a capability source and its request fields.
