# DebugAssist

Crash or vague bug report → evidence-grounded RCA → mitigation → fix → validated PR, with Cloudflare Clef decision models at every decision point.

## LLM providers

The agents (root cause, reproduce, fix) and the LLM fallback for decisions talk to any OpenAI-compatible
API. Two providers are integrated and tested live:

| Provider | Default model | Notes |
|---|---|---|
| **GroqCloud** | `openai/gpt-oss-120b` | Free plan works: tool calling, strict structured outputs, reasoning effort. Free limits are 8K tokens/min and 200K tokens/day per model, so each request is held under a token budget (`LLM_MAX_REQUEST_TOKENS`, default 7000 on Groq). |
| **OpenRouter** | `nvidia/nemotron-3-ultra-550b-a55b:free` | Works without credits (about 50 requests/day on free models). With credits, `openai/gpt-oss-120b` with host pinning. |

Pick one with `LLM_PROVIDER=groq|openrouter` (default: GroqCloud when `GROQ_CLOUD_API` is set, else
OpenRouter) and override the model with `LLM_MODEL`. Capabilities and prices are read per model
(`debugassist.core.llm_models`), so the pipeline adapts: native JSON schema or function calling for
structured output, reasoning effort only where supported, OpenRouter routing only on OpenRouter.
Without any key the LLM runs in mock mode (`--llm mock`, scripted output). Decisions themselves are
made by Cloudflare Clef on Workers AI.

Work in progress — see [docs/PLAN.md](docs/PLAN.md) and [docs/PROGRESS.md](docs/PROGRESS.md).

Not affiliated with Uber or Cloudflare. Inspired by the talk "MCP-Powered Crash Investigation" (Kriti Dangi, Uber, AGNTCon + MCPCon Japan 2026).
