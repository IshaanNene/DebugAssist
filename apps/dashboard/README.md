# DebugAssist dashboard

Next.js 16 (App Router) + Tailwind 4 + React Flow over the DebugAssist API (`packages/api`, port 8400).

```bash
make dashboard   # API on :8400 + this app on :3000
```

Screens: **Inbox** (Vitals + BugDrop with triage and run status) · **Issue / RCA** (root cause, key facts with
grounding badges, evidence timeline, 👍/👎) · **Run** (live pipeline graph over SSE, subagent lanes, agent calls,
decision ledger with thresholds, turns and cost) · **PR panel** (diff, validation proof, Playwright artifacts) ·
**Metrics** (pipeline outcomes, decision quality per D#) · **Marketplace** (skills, agent types, subagents,
templates) · **Chat** (the mock chat inbox).

`API_URL` / `NEXT_PUBLIC_API_URL` point the app at another API (default `http://localhost:8400`).
