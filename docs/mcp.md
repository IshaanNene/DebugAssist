# MCP servers

DebugAssist reaches its evidence through **11 MCP servers** (55 tools), the count the talk describes.
The RCA and fix agents use them over stdio; the deterministic collector calls the same functions
directly. They also work from Claude Code or Claude Desktop through the committed [`.mcp.json`](../.mcp.json).

Every server follows the same rules (`packages/mcp_servers/src/debugassist/mcp_servers/common.py`):

- **Evidence IDs.** Every result carries `evidence_id` (`ev_<source>_<hash>`), stable for the same
  content, so RCA claims can cite exactly what they rest on.
- **Pruned, capped results.** Pagination (`limit`, `offset`, `next_offset`) and a result cap
  (`MCP_MAX_RESULT_CHARS`, default 12,000). Logs are collapsed into templates and traces are summarized;
  raw dumps never reach an agent.
- **PII redaction** on every result (emails, phones, tokens, cards, precise GPS).
- **Read-only by default.** Write tools are policy-gated ([`configs/policies/writes.yaml`](../configs/policies/writes.yaml)),
  dry-run unless called with `dry_run=false` *and* the policy allows, and always written to the audit log.

| Server | Backed by | Tools | Writes |
|---|---|---|---|
| **code-search** (Sourcegraph's role) | the target repos (sandbox worktree during a run) | `list_repos`, `search_code`, `read_file`, `find_symbol`, `find_references`, `blame`, `codeowners_for` | — |
| **crash-analytics** | Vitals | `list_issues`, `get_issue`, `get_crash_group`, `get_session`, `distribution`, `flag_exposure`, `crash_rate_timeseries`, `releases` | — |
| **bug-reports** | BugDrop | `list_reports`, `get_report`, `get_logs`, `get_screenshots`, `get_screenshot_image`, `get_ui_state_timeline` | — |
| **jira** | Jira Cloud (or the local mock) | `get_issue`, `find_open_issue`, `create_issue`, `add_comment`, `link_pr`, `transition` | gated |
| **feature-flags** | Unleash | `list_flags`, `get_flag`, `rollout_history`, `flag_crash_correlation`, `rollback_flag` | gated (`flags.rollback`: approval) |
| **tracing** | Jaeger v2 (query API v3) | `find_traces`, `get_trace` (critical path, errors, slowest spans), `service_dependencies` | — |
| **logging** | Loki | `query_logs` (deduped, repeats collapsed, errors first), `log_stats`, `log_patterns` | — |
| **incidents** | local incidents service | `list_active_incidents`, `incident_details`, `dependency_status` | — |
| **releases** | Vitals sessions + git tags + Unleash | `version_adoption`, `list_releases`, `release_diff`, `rollout_status`, `last_good_and_first_bad` | — |
| **metrics-profiles** | Prometheus + Vitals session samples | `promql` (series summarized), `service_profile`, `session_perf` | — |
| **git-history** | the target repos | `list_tags`, `previous_release`, `commits_between`, `commit_details`, `diff_stats`, `bisect_candidates` | — |

Notes on a few tools:

- `find_traces` searches per server-side entry operation and leaves health checks out, because health
  checks fire every few seconds and would fill any "latest N traces" window.
- `last_good_and_first_bad` gives the commit finder its pruned input: the first version an issue
  appeared in, the release before it, and the size of the commit window between them.
- `get_screenshot_image` returns the image itself (MCP image content) for vision-capable models.

## Configuration

| Variable | Default |
|---|---|
| `VITALS_URL` | `http://localhost:8100` |
| `BUGDROP_URL` | `http://localhost:8200` |
| `INCIDENTS_URL` | `http://localhost:8300` |
| `UNLEASH_URL`, `UNLEASH_ADMIN_TOKEN` | `http://localhost:4242`, the local dev admin token |
| `JAEGER_URL` | `http://localhost:16686` |
| `LOKI_URL` | `http://localhost:3100` |
| `PROMETHEUS_URL` | `http://localhost:9090` |
| `CODE_REPOS` | the `targets/` submodules (`{"name": "/path"}` JSON) |
| `JIRA_*` | live when `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_KEY` are set; `JIRA_PROJECT_KEY` (default `SCRUM`) |
| `MCP_MAX_RESULT_CHARS` | `12000` |

## Running

```bash
uv run --no-sync python -m debugassist.mcp_servers.tracing       # any server, stdio
```

Each server also has a script entry point (`debugassist-mcp-<name>`). From Claude Code, open this repo
and the servers in `.mcp.json` are offered automatically.

## Tests

`packages/mcp_servers/tests/` runs offline against recorded live responses in
`tests/fixtures/live/` (re-record with `tests/fixtures/record_live.py` while the stack is up).
