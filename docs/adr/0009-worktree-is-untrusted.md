# 0009. The agent's worktree is untrusted input to the host

- Status: accepted
- Date: 2026-10-16

## Context
Agents run commands in a network-less container with the run's worktree mounted read-write, but host code
(git for diffs, commits, reverts and pushes; the `grep`, `search_code` and fix-plan walks; the harness config)
worked in that same directory afterwards. The 2026-10-16 engineering audit reproduced two escapes: a `.git`
swapped for a directory whose config set `core.fsmonitor` made host `git diff` run a command, and a symlink to a
`.env` outside the worktree was returned by the host-side `grep` tool. It also found the GitHub App token in
the push URL (so in argv, the persisted error and traces) and the harness config read from the agent's copy.

## Decision
Everything the container can write is treated as hostile input by the host:
- Host git goes through `core.hostgit`: in run directories it never discovers the repository; it uses the
  linked worktree's admin dir, accepted only when that admin dir (outside the worktree) points back at the
  worktree, and always disables hooks and fsmonitor. A run directory without a verified git dir is refused.
- The container mounts `<worktree>/.git` read-only and runs as the host user, `--cap-drop ALL`,
  `no-new-privileges`, `--pids-limit 512`.
- Host-side file walks use `guards.walk_files`: no symlinks followed or returned, no secret files.
- Validation reads `.DebugAssist/pipeline.yaml` from the release tag, never the worktree.
- Credentials reach git through its environment (`http.extraheader`), never a URL or argv; node errors and
  span attributes pass through `redaction.redact_secrets` before they are stored or exported.

## Consequences
- The prompt-level guards (command denylist, path confinement of the agent's own tools) are kept, but only as
  mistake-catchers; the container plus this boundary is the security control.
- Container commands no longer run as root. TypeScript images install corepack shims under `/tmp/bin`. A setup
  step that needs root (an `apk add`) would now fail; none of the onboarded repositories has one.
- The runtime image still trusts every directory (`safe.directory '*'`) for the main checkout, which no agent
  writes; worktree git calls do not depend on it.
- Not done: running the suite with the release's own tests restored (a fix can still edit an existing test),
  a prompt-injection red-team evaluation with canary secrets, and a per-run context instead of `os.environ`.
