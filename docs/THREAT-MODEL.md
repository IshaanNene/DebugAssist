# Threat model

DebugAssist reads text that strangers write (bug reports, GitHub issues, logs, commit messages, code), gives it to
a language model that has a shell, and can write to repositories, trackers and chat. This page says what it
protects, from whom, where the trust boundaries are, and which test holds each control. Decisions behind it:
[ADR 0002](adr/0002-decide-reason-act.md) (deterministic code acts), [ADR 0008](adr/0008-github-app-installations.md)
(the App's opt-in) and [ADR 0009](adr/0009-worktree-is-untrusted.md) (the worktree is untrusted).

## Assets

| Asset | Where it lives | Harm if lost |
|---|---|---|
| Model and Clef keys, Jira, Discord, GitHub token | `.env` on the host (never in a sandbox) | Spend, impersonation |
| GitHub App private key and installation tokens | A file named by `GITHUB_APP_PRIVATE_KEY_PATH`; tokens in memory | Pushes and comments as the app on every installed repository |
| Write access to repositories, trackers, chat, flags | Behind `configs/policies/writes.yaml` | Unreviewed code shipped, noise, a flag changed in production |
| The host (the developer's machine or the worker) | Outside the container | Everything above |
| Ground truth (`groundtruth/`) | The DebugAssist checkout | Evaluation results that mean nothing |
| Reporters' personal data in reports and logs | Run directories, traces | Privacy |

## Actors

- **A reporter or anyone who can write text the agent reads**: an issue body on an installed public repository, a
  log line, a commit message, a code comment, test output. Untrusted. This is the main adversary: prompt injection.
- **The model.** Not malicious, but it follows instructions it should not and makes mistakes; treated as untrusted
  for anything it outputs: commands, file edits, results.
- **A maintainer of an installed repository**: trusted to label issues (the label is the consent to run), not
  trusted with DebugAssist's keys.
- **Someone on the same network as the developer**: untrusted; reaches only what is published on a non-loopback
  interface.
- **The operator** (whoever runs DebugAssist): trusted.

## Boundaries and controls

| Boundary | Threat | Control | Held by |
|---|---|---|---|
| Untrusted text → model | Instructions in data | Fenced as `<untrusted_data>`; the system prompt says data is never instruction; a closing tag inside cannot end the fence | `test_injection.py`, `test_redteam.py` (fence) |
| Untrusted text → model, logs, traces | Personal data and credentials | `redact_text` before a model; `redact_secrets` on errors and span attributes | `test_redaction.py`, `test_graph_errors.py` |
| Model → shell | Destructive or exfiltrating commands | The **container**: `--network none`, host user, `--cap-drop ALL`, `no-new-privileges`, `--pids-limit`, `.git` read-only, only the worktree mounted. The command denylist catches mistakes, not an adversary | `test_hostgit.py` (container flags); live red-team arm (ROADMAP-100 003, not run yet) |
| Model → files | Reading secrets or escaping the worktree | `confine` on every agent file tool; secret-file names refused; `.git` off limits | `test_policy_guards.py`, `test_redteam.py` (confine) |
| Worktree → host | A planted `.git` running a command in host git; a symlink read by a host-side walk | `core.hostgit` (verified git dir, no hooks or fsmonitor); `walk_files` (no symlinks) | `test_hostgit.py`, `test_workspace_tools.py`, `test_redteam.py` (hostgit, walk) |
| Worktree → proof | A fix that edits tests or the harness so "validated" means nothing | The proof runs in a disposable checkout of the release with only the source change and new tests; protected paths and added skips force a flagged draft | `test_proof_path.py`, `test_harness_config.py` |
| Pipeline → outside world | Writes nobody approved | One policy gate for every write, default deny for unknown repositories, bot branches only, draft PRs outside the policy's own repositories; the audit log records what was applied | `test_gated_writes.py`, `test_ship.py`, `test_redteam.py` (policy) |
| Credentials → persisted state | A token in argv reaching an error, `state.json` or a trace | Git authenticates through its environment (`http.extraheader`), never a URL or argv | `test_github_app.py` (failed push) |
| GitHub → webhook | Forged or replayed deliveries | HMAC over the body; delivery id must be a GUID; repeated ids and bodies dropped | `test_api.py` |
| Browser → API | A web page making the browser start paid runs | POSTs need the dashboard's Origin or `DA_API_TOKEN`; the API listens on 127.0.0.1 and refuses another interface without a token | `test_api.py` |
| Network → dev stack | Redis feeding the worker; services with default credentials | Every port on 127.0.0.1 (checked in CI); Redis password; jobs as JSON, never pickle | CI `compose` job, `test_harness.py` |
| Run → run (one process) | One run's code search reading another run's worktree | Run id, mode and code repos are per asyncio task (`core.runctx`), never written to `os.environ` | `test_runctx.py` |
| Developer shell → live writes | An exported `GITHUB_TOKEN` turning pushes live | GitHub goes live only when its token is in this project's `.env` or `DA_MODE_GITHUB=live` | `test_settings.py` |
| Ground truth → agent | Evaluation leaks | Nothing under `groundtruth/` is mounted into a sandbox or referenced from target repos; hidden tests run in a copy | `test_catalog.py` (regression commits name no ground truth); that only the worktree is mounted is in `test_hostgit.py`'s container check |

## Known gaps

- **Exfiltration through what the app writes.** A reporter's issue can ask the model to quote file contents in its
  root cause, which the App posts as a comment. Secret files are refused and output is redacted, but any other
  file in the worktree can be quoted. The repository is the one the reporter filed against, so this exposes
  nothing they could not read — unless the repository is private. Private installations need review.
- **The container is unmeasured against an adversary.** The red-team catalogue is checked offline for every
  control except the container; the live arm (ROADMAP-100 003) has not run.
- **The model can still be wrong in good faith.** A plausible fix with a narrow test passes validation; reviewers
  see a flagged draft only when protected paths or skips change. Fix width is a research problem
  ([ROADMAP.md](ROADMAP.md), P18).
