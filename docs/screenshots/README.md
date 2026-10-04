# DebugAssist screenshots

Proof from live runs against the local MiniRide stack, captured with `make screenshots` (`scripts/screenshots.py`). Nothing here is mocked: the LLM, Clef, GitHub and Jira calls were live.

## 1 · The system under test

A small ride-hailing system built for this project: a React web client plus gateway (Node/GraphQL), dispatch (Python/FastAPI) and payments (Go), all instrumented with OpenTelemetry.

**MiniRide, the rider web app DebugAssist debugs (React PWA), with the in-app 'Report a bug' button** · captured 2026-10-04 10:12 UTC

![MiniRide, the rider web app DebugAssist debugs (React PWA), with the in-app 'Report a bug' button](01-miniride-home.png)

**Jaeger: one rider request traced end to end across dispatch, gateway, miniride-client (9 spans, OpenTelemetry)** · captured 2026-10-04 10:12 UTC

![Jaeger: one rider request traced end to end across dispatch, gateway, miniride-client (9 spans, OpenTelemetry)](02-jaeger-trace.png)

## 2 · Where bugs come from

Crashes flow into Vitals, user bug reports into BugDrop. Release 1.6.1 shipped a real-looking regression behind a 5% feature-flag rollout; tapping a push notification right after launch crashes.

**Vitals (crash analytics): crashes grouped into issues by fingerprint** · captured 2026-10-04 10:12 UTC

![Vitals (crash analytics): crashes grouped into issues by fingerprint](03-vitals-issues.png)

**Vitals VIT-1001: symbolicated stack trace, breadcrumbs, flag exposure and affected versions** · captured 2026-10-04 10:12 UTC

![Vitals VIT-1001: symbolicated stack trace, breadcrumbs, flag exposure and affected versions](04-vitals-issue.png)

**BugDrop: bug reports filed from inside the app** · captured 2026-10-04 10:12 UTC

![BugDrop: bug reports filed from inside the app](05-bugdrop-reports.png)

**BugDrop BD-1001: the user's description, screenshots, UI-state timeline and logs** · captured 2026-10-04 10:12 UTC

![BugDrop BD-1001: the user's description, screenshots, UI-state timeline and logs](06-bugdrop-report.png)

**Unleash: the notif_router_v2 feature flag on a 5% gradual rollout, the flag behind the crash** · captured 2026-10-04 10:12 UTC

![Unleash: the notif_router_v2 feature flag on a 5% gradual rollout, the flag behind the crash](07-unleash-flag.png)

## Jira

Run `uv run --no-sync python scripts/screenshots.py jira-login` once and sign in, then `make screenshots` captures the ticket too.

---
Open-source project; not affiliated with Uber or Cloudflare.
