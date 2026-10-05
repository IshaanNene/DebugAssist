---
description: Gateway responsibilities, upstream calls, CORS and how to test it
---

- TypeScript in `gateway/src/`: `schema.ts` (GraphQL schema and resolvers), `backends.ts` (HTTP calls to
  dispatch and payments), `app.ts` (server, CORS), `notifications.ts` (in-app notifications to clients).
- Tests: `pnpm test` (unit); integration through `./scripts/integration.sh`.
