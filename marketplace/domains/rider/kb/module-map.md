---
description: Where things live in the MiniRide client (modules, entry points, tests, how to run)
---

- `src/main.tsx` boots the app (flags, telemetry, router); `src/App.tsx` holds routes.
- `src/screens/` — one file per screen (Search, RequestRide, RideScreen, Notifications, Layout, CrashScreen).
- `src/api/` — GraphQL client for the gateway (`gql`) and ride requests.
- `src/eta/` — ETA updates while a ride is active.
- `src/notifications/` — push-notification handling and deep-link routing.
- `src/store/` — persisted session state.
- `src/flags.ts` — OpenFeature + Unleash; flags can be overridden in dev builds only.
- `src/telemetry/` — Vitals SDK, analytics, tracing, BugDrop report capture.
- Tests: `test/*.test.ts` (Vitest, jsdom); E2E: `e2e/*.spec.ts` (Playwright against :8080).
- Checks CI runs: `pnpm lint && pnpm typecheck`, `pnpm test`.
