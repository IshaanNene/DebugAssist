# 0010. Concurrency model: one run per process, the poller runs them one at a time

- Status: accepted
- Date: 2026-10-17

## Context
Until now nothing said what may share a process. The audit (P3-15) found runs writing `os.environ`, which only
works if a process holds one run; the API builds deps for concurrent requests; the poller spawns runs; agents run
subagents in parallel; the decision engine sends chunks concurrently. Each of those assumed something different.

## Decision
- **A run owns a process.** `debugassist run` (CLI, poller, worker) executes one issue. Its graph, sandbox
  worktree (`.data/runs/<id>/repo`), checkpoints and run directory belong to it alone.
- **Inside a run, concurrency is asyncio tasks, and per-run values are per task.** Run id, mode and code repos
  live in `core.runctx` (a context variable set around every node), never in `os.environ`. Subagents and decision
  chunks run as tasks within the run; MCP servers are child processes with the values in their environment.
- **The poller is a scheduler, not a worker.** It holds `.data/app/poll.lock` (one poller per checkout), picks
  work, starts one run process at a time and records the result in `seen.json` (written atomically). A webhook
  delivery stays in `queue/processing/` until its run ends.
- **The API serves; it does not run graphs concurrently in-process.** POSTs that start work spawn a run process
  (diff fixer, runs) or append to files. Reads go through the run index.
- **Shared files are append-only or atomic.** The audit log and event logs are append-only JSON lines; state,
  node files, `seen.json`, metrics and the run index are written to a temporary file and renamed.

## Consequences
- Throughput is one run at a time per poller: about 10 an hour at the median run time measured on 2026-10-17
  (`debugassist eval latency`). More needs more pollers on separate checkouts, or the worker pool of
  ROADMAP-100 046 with one run per repository at a time.
- Nothing in a run may assume it is the only run on the machine except its own run directory and worktree; two
  pollers on two checkouts are safe, two on one checkout are refused by the lock.
- A feature that needs two runs to cooperate (cross-repo hand-off) does so through files and the run state, not
  shared memory.
