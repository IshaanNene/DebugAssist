# DebugAssist developer entry points. Everything works without API keys (mock mode).
SHELL := /bin/bash
COMPOSE := docker compose -f infra/docker-compose.yml
PROFILES ?= core obs flags faults
PROFILE_FLAGS := $(foreach p,$(PROFILES),--profile $(p))

.PHONY: help sync bootstrap lint fmt typecheck test check up down ps logs clean clef-smoke

help:  ## List targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

sync:  ## uv sync + clear macOS hidden flag on .pth files (Python 3.13 skips hidden .pth)
	uv sync
	@if [ "$$(uname)" = Darwin ]; then chflags nohidden .venv/lib/python3.*/site-packages/*.pth; fi

bootstrap: sync  ## Install Python deps and git hooks
	uv run pre-commit install

lint:  ## Ruff lint + format check
	uv run ruff check .
	uv run ruff format --check .

fmt:  ## Auto-fix lint and format
	uv run ruff check --fix .
	uv run ruff format .

typecheck:  ## Pyright (strict)
	uv run pyright

test:  ## Unit tests (mock mode)
	uv run pytest

check: lint typecheck test  ## Everything CI runs

up:  ## Start infra (PROFILES="core obs flags faults")
	$(COMPOSE) $(PROFILE_FLAGS) up -d --wait

down:  ## Stop infra (keeps volumes)
	$(COMPOSE) --profile '*' down

ps:  ## Show infra status
	$(COMPOSE) --profile '*' ps

logs:  ## Tail infra logs (SERVICE=name to filter)
	$(COMPOSE) --profile '*' logs -f --tail=100 $(SERVICE)

clean:  ## Stop infra and delete volumes
	$(COMPOSE) --profile '*' down -v

clef-smoke:  ## One live Clef + Clef-flash call (needs CLOUDFLARE_* in .env; ~$0.0001)
	scripts/clef_smoke.sh
