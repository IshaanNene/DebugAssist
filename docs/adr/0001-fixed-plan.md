# 0001. The pipeline plan is fixed in code

- Status: accepted · Date: 2026-10-04

## Context
The talk's central design choice: "we control the plan". Letting an LLM plan the workflow adds a class of hallucinations (skipped validation, invented steps) and makes runs hard to compare.

## Decision
The pipeline is a static LangGraph `StateGraph` (N0–N9). Conditional edges exist only where the spec defines them (early exit after categorisation, validation retry loop, ship-gate outcomes) and are chosen by Clef decisions through policy YAML or by deterministic code — never by an LLM. LLM nodes have per-node config (model, reasoning effort, max turns, budget).

## Consequences
Runs are comparable and auditable; new behaviour arrives as skills/plugins/subagents, not graph changes. Some flexibility is lost; the D6 evidence loop gives bounded flexibility inside the RCA node.
