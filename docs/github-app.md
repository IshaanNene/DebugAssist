# The GitHub App

Label an issue `debugassist` on a repository the app is installed on, and DebugAssist investigates it: it checks
the repository out at its default branch, runs the pipeline (triage → root cause → reproduction test → fix →
validation), comments the root cause on the issue and, when a fix validates, opens a **draft** pull request from a
`debugassist/*` branch.

```
issue labeled "debugassist"
  └─ debugassist app poll  (or the API's /github/webhook → queue)
       └─ debugassist run GHA:owner/repo#123
            ├─ targets/gh--owner--repo  ← clone at the default branch, tagged vapp-<sha>
            ├─ pipeline, in the network-less sandbox
            ├─ comment on the issue  (root cause, where, introduced by, PR link)
            └─ draft PR  debugassist/… → default branch
```

## What it may do

- **Repositories:** every repository the app is installed on (`app_installations: true` in
  [`configs/policies/writes.yaml`](../configs/policies/writes.yaml)), plus the two MiniRide repositories listed
  there. Installing the app on a repository is the opt-in; uninstalling it, or setting `app_installations: false`,
  takes the repository away. If the app's API cannot be reached, nothing is allowed.
- **Only with a pipeline config:** a repository runs only once it carries `.DebugAssist/pipeline.yaml` on its
  default branch ([onboarding](#onboarding-a-repository)); otherwise the issue gets one comment saying so.
- **Writes:** comments on the labeled issue; pushes to `debugassist/*` branches only (never the default branch,
  `release/*` or tags); pull requests as drafts. Every write goes through the policy gate and the audit log
  (`.data/audit.jsonl`).
- **Secrets:** the private key stays in a file outside the repository, read by path; installation tokens live an
  hour, are used on the host only (REST and `git push` over HTTPS), and never enter the sandbox. The checkout's
  remote is reset to the plain URL after cloning.

## Creating the app

1. GitHub → Settings → Developer settings → GitHub Apps → **New GitHub App** (or for an organisation, its
   settings). Name it, e.g. `DebugAssist (yourname)`; homepage: this repository.
2. **Permissions** (repository): Issues — read & write; Pull requests — read & write; Contents — read & write;
   Metadata — read. **Events:** Issues.
3. **Webhook:** off for polling only; on, with a URL and a secret, for the [webhook](#webhook-optional).
4. Create it, note the **App ID**, and generate a **private key** (a `.pem` download). Keep it outside the repo,
   e.g. `~/.config/debugassist/github-app.pem`, readable only by you (`chmod 600`).
5. **Install** the app on the repositories it should work on (Install App → Only select repositories).

The same, as an app manifest (Settings → Developer settings → GitHub Apps → New GitHub App from a manifest):

```json
{
  "name": "DebugAssist",
  "url": "https://github.com/IshaanNene/DebugAssist",
  "public": false,
  "default_permissions": { "issues": "write", "pull_requests": "write", "contents": "write", "metadata": "read" },
  "default_events": ["issues"],
  "hook_attributes": { "url": "https://smee.io/your-channel", "active": false }
}
```

## Configuring DebugAssist

In `.env` (never committed):

```
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY_PATH=~/.config/debugassist/github-app.pem
GITHUB_APP_WEBHOOK_SECRET=…   # only with the webhook
GITHUB_APP_LABEL=debugassist  # the default
```

The LLM provider and Docker (for the sandbox) are needed as for any live run. `DA_MODE_GITHUB_APP=mock` uses a
local stand-in (`.data/mock/github-app/state.json`: installations, issues, comments) — the tests use it.

```bash
debugassist app status          # installed repositories, and whether the policy allows each
debugassist app poll --once --dry   # what would run
debugassist app poll            # every 60 s: run each labeled issue once, one at a time
```

An issue that already has the app's comment is not run again by the poll; delete the comment to rerun it.

## Onboarding a repository

Add `.DebugAssist/pipeline.yaml` to the default branch — how to install, test and lint it:

```yaml
version: 1
repo: widgets
default_agent_type: github-issue
bot_branch_prefix: debugassist/
components:
  .:
    path: .
    language: python
    owner: maintainers
    setup: uv venv -q .venv && uv pip install -q -p .venv -e . pytest
    lint: "true"
    test: .venv/bin/python -m pytest -q
    test_one: .venv/bin/python -m pytest -q {file}
    test_file_glob: "tests/test_*.py"
```

The sandbox has no network after `setup`; the test command must work offline.

## Webhook (optional)

The API (`make dashboard`, port 8400) accepts deliveries at `POST /github/webhook`, checks
`X-Hub-Signature-256` against `GITHUB_APP_WEBHOOK_SECRET`, and queues `issues` events with action `labeled` and
the app's label for the poll (which still does the work). On a laptop, relay with
[smee.io](https://smee.io): `npx smee-client --url https://smee.io/your-channel --target http://localhost:8400/github/webhook`,
and set that URL as the app's webhook URL.

## Not yet

Measured only in mock mode and unit tests so far (no app has been created for this project yet). Open: running
on a pull request's CI failure, a hosted worker instead of a laptop poll, per-repository LLM budgets, and the PR
comment loop (`@debugassist fix the diff`) for app repositories.
