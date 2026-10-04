# 0002. Clef decides, the LLM reasons, deterministic code acts

- Status: accepted · Date: 2026-10-04

## Context
Decision points (triage, routing, grounding, mitigation, ship gate) need fast, calibrated, typed answers. LLM self-reported confidence is poorly calibrated and needs output parsing.

## Decision
Every decision point (D1–D18) is a versioned YAML template answered by Clef or Clef-flash on Workers AI. A policy band (act / escalate / safe default) maps probabilities to actions. Every call is recorded in a decision ledger. Writes happen only in deterministic code behind a policy gate. Baselines: an LLM decider (gpt-oss-120b via system-one-adapter) and rules.

## Consequences
Decisions are measurable per D# (accuracy, Brier, ECE) and ablatable. Hard caps (max turns, retry limits) are never removed in favour of Clef.
