---
name: pr-authoring
description: How DebugAssist writes a pull request for a fix — sections, evidence, proof, risk and rollback. Use when opening or describing a PR for a bug fix.
---

# Writing a fix PR

A reviewer should be able to approve or reject the PR from its description alone, without opening the
run. Lead with what broke and for whom, then why, then the proof.

Rules:
- **Summary first**: two or three sentences a busy engineer can act on; link the user-facing issue
  (Vitals crash or BugDrop report) and the ticket.
- **Root cause** names the defect and the mechanism, the file and function, the commit that introduced
  it, and any feature flag gating the path.
- **Evidence**: every claim carries the evidence ids it rests on; mark claims a grounding check could not
  verify. Never present an unverified claim as fact.
- **Test proof** is mandatory for a ready PR: the reproduction test, at which tier (unit, integration, or
  E2E with the user's environment emulated), failing on the release and passing with the fix, plus the
  full suite and the repository's CI checks. Without proof the PR is a draft and says so.
- **Risk & rollback**: the blast radius in one line, how to roll back (revert, flag off), and what to watch
  after the deploy.
- No secrets, no personal data, no internal tooling noise. Plain markdown, short tables, details blocks for
  long output.

The pipeline renders the template below; each `{{section}}` is filled from the run (sections with
nothing to say are dropped with their heading). Edit the template to change every PR DebugAssist opens.

```template
## Summary
{{summary}}

{{links}}

## Root cause
{{root_cause}}

## Evidence
{{evidence}}

## Mitigation
{{mitigation}}

## Fix
{{fix}}

## Test proof
{{test_proof}}

## Risk & rollback
{{risk_rollback}}

---
{{footer}}
```
