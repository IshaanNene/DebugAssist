# 0003. Deterministic context collector with pruning

- Status: accepted · Date: 2026-10-04

## Context
Logs and traces run to MBs/GBs. Fetching from known APIs needs no LLM; doing it inside an agent loop adds latency, cost and context bloat.

## Decision
N2 is plain code: fetch from Vitals, BugDrop, Loki, Jaeger, Prometheus, Unleash, releases; window, session-filter, dedupe, collapse repeats, error-first sample, symbolicate; then Clef-flash relevance scoring (D3) to fit a token budget. Output is an evidence store with stable content-hashed evidence IDs.

## Consequences
LLM nodes start from a compact, citable bundle; they can still pull more through MCP (D6), bounded by turn caps.
