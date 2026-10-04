# Scripted LLM output: push-crash (BUG-002)

Used by `--llm mock` (`make demo-push-crash`) so the whole pipeline runs without an LLM key. Each
`<node>.json` holds a node's structured output and the tool calls it made; `<node>.patch` is applied
to the sandbox worktree. Results are labelled `mode: mock` everywhere they appear.

Derived from live run `20261004-090058-vit-1001` (Nemotron 3 Ultra via OpenRouter): the RCA output,
reproduction test and source change are that run's. Two edits: the test drops two unused imports
(the live run's version failed the target repo's lint, which the pipeline now checks), and the fix
summary is written here because that run's fix agent hit its turn cap before submitting one.
