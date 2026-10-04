# DebugAssist developer entry points. Everything works without API keys (mock mode).
SHELL := /bin/bash
COMPOSE := docker compose -f infra/docker-compose.yml
PROFILES ?= core obs flags faults target sources
PROFILE_FLAGS := $(foreach p,$(PROFILES),--profile $(p))

.PHONY: help demo-push-crash report readme-assets screenshots targets seed flags e2e sync bootstrap sync-sdks trigger inject reset-scenario scenarios verify-scenarios traffic load lint fmt typecheck test check up down ps logs clean clef-smoke

help:  ## List targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

sync:  ## uv sync + sitecustomize path hook (macOS hides .pth files under ~/Desktop dot-dirs)
	uv sync
	@uv run --no-sync python scripts/venv_path_hook.py

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

up:  ## Build and start the stack (PROFILES="core obs flags faults target")
	$(COMPOSE) $(PROFILE_FLAGS) up -d --build --wait

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

flags:  ## Create MiniRide feature flags in Unleash (idempotent)
	uv run --no-sync python infra/unleash/bootstrap.py

e2e:  ## Playwright E2E against the running stack (client on :8080)
	cd targets/miniride-client && pnpm exec playwright test

targets:  ## Fetch the MiniRide target repos (submodules; miniride-services is private)
	git submodule update --init --recursive

seed: flags  ## Seed local state (flags today; BugDrop/Vitals data in P2b)

sync-sdks:  ## Vendor the BugDrop/Vitals SDKs into the MiniRide repos
	mkdir -p targets/miniride-client/src/vendor/vitals targets/miniride-client/src/vendor/bugdrop
	cp sources/vitals/sdk-js/src/*.ts targets/miniride-client/src/vendor/vitals/
	cp sources/bugdrop/sdk-js/src/*.ts targets/miniride-client/src/vendor/bugdrop/
	cp sources/vitals/sdk-py/vitals_sdk.py targets/miniride-services/dispatch/src/dispatch/vitals_sdk.py
	mkdir -p targets/miniride-services/payments/internal/vitals
	cp sources/vitals/sdk-go/vitals/vitals.go targets/miniride-services/payments/internal/vitals/vitals.go
	cp sources/vitals/sdk-node/vitals.ts targets/miniride-services/gateway/src/vitals.ts

scenarios:  ## List catalog bugs
	uv run --no-sync debugassist scenario list

inject:  ## Inject a catalog bug: make inject BUG=002
	uv run --no-sync debugassist scenario inject $(BUG)

trigger:  ## Inject (if needed) and run a bug's rider scenario: make trigger BUG=001
	uv run --no-sync debugassist scenario trigger $(BUG)

demo-push-crash:  ## BUG-002 end to end with no keys: scripted LLM, mock Clef/GitHub/Jira/Slack (LIVE=1: real everything)
	uv run --no-sync debugassist scenario trigger 002
	$(if $(LIVE),,DA_MODE_LLM=mock DA_MODE_CLEF=mock DA_MODE_GITHUB=mock DA_MODE_JIRA=mock DA_MODE_SLACK=mock) uv run --no-sync debugassist run latest --llm $(if $(LIVE),live,mock)
	uv run --no-sync debugassist report

report:  ## Render the latest run (or RUN=<id>) as .data/runs/<id>/report.html
	uv run --no-sync debugassist report $(RUN)

readme-assets:  ## Rebuild README visuals: hero, overview, pipeline, MiniRide, logo wall (SVG) and demo GIF (needs ffmpeg)
	uv run --no-sync python scripts/readme_assets.py $(or $(WHAT),all)

screenshots:  ## Proof screenshots into docs/screenshots/ (WHAT=stack|run|all; Jira: scripts/screenshots.py jira-login once)
	uv run --no-sync python scripts/screenshots.py $(or $(WHAT),all)

reset-scenario:  ## Back to the clean release (WIPE=1 also wipes Vitals/BugDrop/ride data)
	uv run --no-sync debugassist scenario reset $(if $(WIPE),--wipe,)

verify-scenarios:  ## Catalog integrity: regression applies, hidden test fails, fix passes
	uv run --no-sync debugassist scenario verify

traffic:  ## Normal rider traffic through the browser fleet (SESSIONS=20)
	uv run --no-sync python -c "import asyncio; from debugassist.simulator.scenarios import run_scenario; print(asyncio.run(run_scenario('normal_traffic', {'sessions': $(or $(SESSIONS),20)})))"

load:  ## Locust backend load on the gateway (USERS=20 DURATION=60s)
	uv run --no-sync --with locust locust -f packages/simulator/src/debugassist/simulator/locustfile.py --headless -u $(or $(USERS),20) -r 5 -t $(or $(DURATION),60s) --host http://localhost:4000 --only-summary
