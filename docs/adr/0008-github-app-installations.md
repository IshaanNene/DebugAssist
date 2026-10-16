# 0008. The GitHub App: an installation is the opt-in for writes

- Status: accepted · Date: 2026-10-16 · Amends the "Safety" rule (pushes only to the two MiniRide repositories)

## Context
Until now DebugAssist wrote only to `debugassist/*` branches of `IshaanNene/miniride-client` and
`IshaanNene/miniride-services`, a hard list in `configs/policies/writes.yaml`. A GitHub App lets it work on other
repositories: someone labels an issue, it investigates, comments the root cause and opens a draft PR. The
question was which repositories it may write to.

## Decision
- **An installation is the opt-in.** With `app_installations: true` in the write policy, a repository the app is
  installed on counts as allowed, alongside the listed ones. The owner chooses by installing the app; uninstalling
  it, or turning the flag off, removes the repository. If the installation list cannot be fetched, nothing extra is
  allowed.
- **A pipeline config is the second opt-in.** Nothing runs on a repository without `.DebugAssist/pipeline.yaml`
  on its default branch; the issue gets one comment explaining how to add it.
- **Everything else is unchanged:** `debugassist/*` branches only (never the default branch, `release/*` or
  tags), draft PRs only, every write through the policy gate and the audit log, dry-run for anything the policy
  does not list. The private key is read from a file outside the repository; installation tokens are used on the
  host only and never enter the sandbox.
- **Delivery:** a poll (`debugassist app poll`, no public URL needed) plus a signature-checked webhook that only
  queues work for it.

## Consequences
- The write surface grows to whatever the owner installs the app on; the policy flag is the off switch.
- Runs on unknown repositories depend on their `pipeline.yaml` working offline in the sandbox.
- Not exercised live yet: no app has been created for this project; the tests use a fake GitHub API and the mock.
