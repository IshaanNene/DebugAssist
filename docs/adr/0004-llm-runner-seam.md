# 0004. LLM calls go through an `LLMRunner` seam (OpenRouter gpt-oss-120b; record/replay mocks)

- Status: accepted · Date: 2026-10-04

## Context
The spec assumed the Claude Agent SDK. Review amendment A1 replaced it with OpenRouter `openai/gpt-oss-120b`. Mock mode must work without keys and without patching any SDK.

## Decision
LLM nodes depend on an `LLMRunner` protocol. Implementations: `LangChainAgentRunner` (live: LangChain `create_agent`, `ChatOpenAI` pointed at OpenRouter, MCP tools via `langchain-mcp-adapters`, middleware for turn caps and guards), `CassetteRunner` (replays recorded live runs), `ScriptedRunner` (deterministic per-bug scripts, labelled mock). Results carry `mode`.

## Consequences
Provider can change without touching nodes. We implement our own sandboxed coding tools (read/edit/grep/run) and skill loading. Mock results are never reported as eval results.
