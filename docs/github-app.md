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

An issue that already has the app's comment, or that the poll has already run (`.data/app/seen.json`), is not
run again by the poll. With the webhook connected, removing and re-adding the label reruns it (each delivery is
queued once: a repeated delivery id or body is dropped); with the poll alone, `debugassist app rerun
GHA:owner/repo#123` queues it again.

A failed run is retried twice, 5 and then 10 minutes later (`RETRY_BASE` = 300 s, doubling; `MAX_ATTEMPTS` = 3); after the third failure the issue gets a comment
saying the analysis could not finish. Comments and labeled issues are read across all pages, and the list of
installed repositories is refreshed every 10 minutes (`REPOS_TTL` = 600 s).

Pull requests on an installed repository are always drafts: the policy's own `repos` list is the only place a
ready-for-review PR can open, whatever the ship decision proposes.

## Onboarding a repository

Add `.DebugAssist/pipeline.yaml` to the default branch — how to install, test and lint it:

```yaml
version: 1
repo: widgets
default_agent_type: github-issue
bot_branch_prefix: debugassist/
run_budget_usd: 1.00   # optional: what one run on this repository may spend (never above the global $5 cap)
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

## Operations

Everything the app does on this machine lives under `.data/`:

| What | Where |
|---|---|
| The poll's memory (one entry per issue: result, attempts, time) | `.data/app/seen.json` |
| Webhook deliveries waiting, and the ones being run | `.data/app/queue/`, `.data/app/queue/processing/` |
| Delivery ids and bodies already seen (replay guard) | `.data/app/deliveries/` |
| One poller at a time | `.data/app/poll.lock` |
| A run's state, node files, worktree and trace id | `.data/runs/<run id>/` |
| Every write the app asked to make, and what happened | `.data/audit.jsonl` |
| The checkout of an installed repository | `targets/gh--<owner>--<repo>/` |

**Start and stop.** `debugassist app poll` runs in the foreground; stop it with Ctrl-C. A second `poll` refuses to
start while one holds the lock. A run in progress is its own `debugassist run GHA:…` process: stopping the poll
does not stop it, and a webhook delivery stays in `queue/processing/` until its run ends, so nothing is lost.

**Read what happened.** `debugassist app poll` prints one line per issue and its exit code. For a run, the CLI
summary and `.data/runs/<id>/state.json`; the dashboard (`make dashboard`) shows the same; the trace id in the
state opens the run in Phoenix or Langfuse. `grep '"github.comment"' .data/audit.jsonl` lists every comment the app
asked to post, with the policy's verdict and whether it was applied.

**A run failed.** It is retried at 5 and 10 minutes; after the third failure the issue gets a comment saying so.
Read the run's `errors` in `state.json` (credentials are redacted before they are stored), fix the cause, then
`debugassist app rerun GHA:owner/repo#123`.

**Stop the app acting on one repository.** Uninstall the app there (it drops off within 10 minutes), or set
`app_installations: false` in `configs/policies/writes.yaml` to stop it on all of them at once. Each run reads the
policy when it starts and the poll when it starts, so restart the poll for its own comments to follow the change.

**The private key leaked.** In the app's settings on GitHub, generate a new private key and delete the old one
(installation tokens made from it expire within the hour), point `GITHUB_APP_PRIVATE_KEY_PATH` at the new file,
and restart the poll. Rotate `GITHUB_APP_WEBHOOK_SECRET` the same way if the relay URL was shared.

## Review comments

On a pull request the app opened, a comment that starts with `@debugassist` from the repository's owner, a member
or a collaborator asks for a revision: `@debugassist keep the old signature`. The webhook queues it
(`.data/app/reviews/`), the next poll pass finds the run that opened the PR and hands the instruction to the diff
fixer, which revises the fix, re-validates it against the release, pushes and comments — each write through the
policy gate. Comments from anyone else, from bots, or on issues are ignored: a revision spends the operator's
credit.

## Scale

The target today is a handful of repositories on one machine, not a fleet: one poller runs one issue at a time
([ADR 0010](adr/0010-concurrency-model.md)). Measured on this project's stored runs (`debugassist eval latency`,
75 runs, 2026-10-14 → 17): a run takes 347 s at the median and 656 s at p95, so one poller finishes about 10
issues an hour, fewer when fixes retry. The bottleneck is the model time in `classify_rca` (p50 135 s) and `fix`
(p50 159 s); polling itself makes about one API call per installed repository per pass plus one per labeled issue not yet run,
well inside GitHub's 5,000 an hour per installation. Beyond that: the worker pool with one run per repository
(ROADMAP-100 046) and webhooks as the primary path.

## Not yet

Measured only in mock mode and unit tests so far (no app has been created for this project yet). Open: running
on a pull request's CI failure and a hosted worker instead of a laptop poll.
