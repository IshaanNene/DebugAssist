# DebugAssist for coding agents

A coding agent (Claude Code, Cursor, Codex) can hand DebugAssist an issue and read back the root cause and the proof,
through an MCP server in this checkout (`debugassist.mcp_servers.investigator`, ROADMAP-100 080).

```bash
claude mcp add debugassist -- uv run --directory /path/to/DebugAssist python -m debugassist.mcp_servers.investigator
```

| Tool | What it does |
|---|---|
| `investigate(issue, llm="mock")` | Starts `debugassist run <issue>` in its own process and returns at once (a run takes minutes). `issue` is `VIT-1001`, `BD-1003`, `latest` or `GHA:owner/repo#123`. `llm="live"` uses real models and spends money; the default is the mock. |
| `runs(issue=None, limit=10)` | Runs newest first, of one issue when given: run id, status, outcome. |
| `report(run_id)` | The root cause (summary, category, location, claims with their evidence ids, fix direction), the validation proof (fails on the release, passes with the fix, the suite, anything flagged), the outcome and the PR. |

The server reads run state files and starts runs; it writes nothing else. A run it starts is an ordinary run: its
writes (PR, comments, tickets) go through the write policy and the audit log like any other, and in mock mode
there are none outside `.data/`.

A skill for the coding agent can be as small as:

```markdown
---
name: debugassist
description: Investigate a production crash or bug report with DebugAssist and use its root cause and proof.
---
When the user asks about a crash or bug report by id (VIT-…, BD-…, GHA:…), call the debugassist `investigate`
tool, wait about a minute, call `runs` with the same issue for the run id, then `report`. Quote the root cause with
its evidence ids, say whether validation passed, and link the PR if there is one. Use `llm="live"` only when the
user asks for a live run.
```
