---
description: Payments service layout, pricing inputs and how to test it
---

- Go module in `payments/`: `main.go` (HTTP handlers), `internal/fares` (fare calculation and its tests),
  `internal/flags`, `internal/telemetry`, `internal/vitals`.
- Amounts are integer cents in the city's currency.
- Tests: `go test ./...`; `go vet ./...` runs in CI.
