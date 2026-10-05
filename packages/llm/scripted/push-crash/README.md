# Scripted LLM output: push-crash (BUG-002)

Used by `--llm mock` (`make demo-push-crash`) so the whole pipeline runs without an LLM key. Each
`<node>.json` holds a node's structured output and the tool calls it made; `<node>.patch` is applied
to the sandbox worktree. Results are labelled `mode: mock` everywhere they appear.

Derived from live run `20261004-090058-vit-1001` (Nemotron 3 Ultra via OpenRouter, final attempt on
2026-10-04): the RCA output, the reproduction test, the source change and the fix summary are that
run's, unedited. It passed validation (fails before, passes after, suite and lint/typecheck) and the
target repo's CI.
