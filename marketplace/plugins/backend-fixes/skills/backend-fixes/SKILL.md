---
name: backend-fixes
description: Fix conventions for MiniRide services — gateway (TypeScript/GraphQL), dispatch (Python/FastAPI), payments (Go). Use when the defect is in a backend service.
---

# Fixing a backend defect

- **Fix at the boundary that owns the invariant.** Validate input where it enters the service; keep
  handlers thin; put business rules in the module that owns them.
- **Errors are part of the contract.** Return the service's existing error shape and status codes; never
  swallow an error to make a test pass; log once, with the request/trace id.
- **Timeouts and retries come in pairs.** A caller's timeout must exceed the callee's worst case at the
  expected load; anything retried must be idempotent (or carry an idempotency key end to end).
- **Nil/None safety.** In Go, check errors and nil pointers before use; in Python, handle `None` from
  optional fields explicitly; in TypeScript, avoid non-null assertions on data from other services.
- **Keep migrations and config changes separate** from code fixes unless the fix needs them, and say so.
- **Tests:** a unit test for the faulty function plus, when the bug crosses services, an integration test
  through the public API (`./scripts/integration.sh` runs against the compose stack).
- Run the service's own checks: `pnpm lint && pnpm typecheck`, `uv run ruff check .`, `go vet ./...`.
