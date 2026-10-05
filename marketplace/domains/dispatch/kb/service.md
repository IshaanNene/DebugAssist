---
description: Dispatch service layout, data model, APIs and how to test it
---

- Python package in `dispatch/src/dispatch/`: `app.py` (FastAPI routes), `db.py` (SQLAlchemy + Postgres),
  `matching.py` (driver matching), `geo.py`, `flags.py`, `telemetry.py`.
- Ride statuses used in code: `searching`, `matched`, `driver_assigned`, `arriving`, `completed`.
- Called by the gateway only; emits OpenTelemetry traces and JSON logs (service name `dispatch`).
- Tests: `uv run pytest -q` in `dispatch/` (unit, `tests/`), `./scripts/integration.sh` (through the gateway).
