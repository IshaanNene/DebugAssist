"""Inject a catalog bug into the running stack, and reset back to the clean release.

Injection = for every repo the bug touches: branch `release/<version>` from the base tag, apply
the regression commit(s) with `git am` (natural authors and messages), cut the release with the
repo's own `scripts/release.sh`, rebuild and restart the affected services. Then flip flags,
add network/database toxics, declare incidents — whatever the scenario needs.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from debugassist.scenarios.catalog import ROOT, Bug
from debugassist.scenarios.environment import Environment
from debugassist.scenarios.targets import COMPOSE_SERVICES, TargetRepo

STATE = ROOT / ".data" / "scenario.json"
PREV_CLIENT = ROOT / ".data" / "builds" / "client-prev"
COMPOSE = ["docker", "compose", "-f", str(ROOT / "infra" / "docker-compose.yml")]
PROFILES = ["core", "obs", "flags", "faults", "target", "sources"]
FLAG_PROPAGATION_S = 8  # services poll Unleash every 5 s


# Docker races that a second try gets past (a dependency recreated while another service still points at it).
TRANSIENT = ("No such container", "dependency failed to start", "is already in progress")


def compose(*args: str, profiles: list[str] = PROFILES, attempts: int = 3) -> None:
    cmd = [*COMPOSE, *[f for p in profiles for f in ("--profile", p)], *args]
    for attempt in range(attempts):
        out = subprocess.run(cmd, capture_output=True, text=True)
        if out.returncode == 0:
            return
        if attempt + 1 < attempts and any(t in out.stderr for t in TRANSIENT):
            time.sleep(5)
            continue
        raise RuntimeError(f"{' '.join(cmd)}\n{out.stderr[-3000:]}")


@dataclass
class InjectionResult:
    bug: str
    branches: dict[str, str]
    services: list[str]
    flags: dict[str, int]
    incidents: list[str]
    previous_client: str | None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__ | {"at": datetime.now(UTC).isoformat()}


def current() -> dict[str, Any] | None:
    return json.loads(STATE.read_text()) if STATE.is_file() else None


def inject(
    bug: Bug, env: Environment, *, push: bool = False, previous_client: bool = True, log: Any = print
) -> InjectionResult:
    inj = bug.injection
    active = current()
    if active:
        raise RuntimeError(f"scenario {active['bug']} is active; run `debugassist scenario reset` first")
    repos = [TargetRepo(name) for name in inj.repos]
    for repo in repos:
        if not repo.is_clean():
            raise RuntimeError(f"{repo.name} has uncommitted changes; commit or stash them first")
    branches: dict[str, str] = {}
    services: list[str] = []
    for repo in repos:
        assert inj.release, f"{bug.id}: code injection needs a release version"
        branch = repo.checkout_release(inj.base, inj.release)
        for rel in inj.repos[repo.name]:
            repo.apply_patch(bug.path(rel))
        repo.release(inj.release)
        log(
            f"{repo.name}: {branch} = {inj.base} + {len(inj.repos[repo.name])} commit(s), tagged v{inj.release}"
        )
        if push:
            repo.push(branch, f"v{inj.release}")
            log(f"{repo.name}: pushed {branch} and v{inj.release}")
        branches[repo.name] = branch
        services += repo.services
    prev = None
    if previous_client and "miniride-client" in inj.repos:
        # Gradual adoption: the previous release keeps serving a share of sessions on :8081.
        shutil.rmtree(PREV_CLIENT, ignore_errors=True)
        TargetRepo("miniride-client").export_tree(inj.base, PREV_CLIENT)
        services.append("client-prev")
        prev = inj.base
    if services:
        log(f"rebuilding {', '.join(services)} …")
        compose("up", "-d", "--build", "--wait", *services, profiles=[*PROFILES, "rollout"])
    for flag, pct in inj.flags.items():
        env.set_rollout(flag, pct)
        log(f"flag {flag} → {pct}% gradual rollout")
    if inj.flags:
        time.sleep(FLAG_PROPAGATION_S)  # services poll Unleash every 5 s; traffic must see the new rollout
    for t in inj.toxics:
        env.add_toxic(t)
        log(f"toxic {t.type} on {t.proxy}: {t.attributes}")
    incidents = [env.declare_incident(i) for i in inj.incidents]
    for name, status in inj.dependencies.items():
        env.set_dependency(name, status)
    result = InjectionResult(bug.id, branches, services, inj.flags, incidents, prev)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(result.as_dict(), indent=2))
    return result


DEPLOYS = ROOT / ".data" / "deploys.jsonl"


def deploy(repo_name: str, ref: str, *, log: Any = print) -> dict[str, Any]:
    """Ship `ref` (a merged release branch, or a bot branch standing in for the merge) to the local stack
    and record when, so a post-merge watch can compare before and after."""
    repo = TargetRepo(repo_name)
    if not repo.is_clean():
        raise RuntimeError(f"{repo_name} has uncommitted changes; commit or stash them first")
    sha = repo.checkout_ref(ref)
    log(f"{repo_name}: deploying {ref} ({sha}); rebuilding {', '.join(repo.services)} …")
    compose("up", "-d", "--build", "--wait", *repo.services)
    entry = {"repo": repo_name, "ref": ref, "sha": sha, "at": datetime.now(UTC).isoformat()}
    with DEPLOYS.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def deploys() -> list[dict[str, Any]]:
    return [json.loads(line) for line in DEPLOYS.read_text().splitlines()] if DEPLOYS.is_file() else []


def reset(env: Environment, *, wipe: bool = False, log: Any = print) -> None:
    state = current()
    touched = list((state or {}).get("branches", {})) or list(COMPOSE_SERVICES)
    for name in touched:
        repo = TargetRepo(name)
        if repo.head() != "main":
            repo.checkout_main()
            log(f"{name}: back on main")
    services = [s for name in touched for s in COMPOSE_SERVICES[name]]
    log(f"rebuilding {', '.join(services)} …")
    compose("up", "-d", "--build", "--wait", *services)
    compose("rm", "-sf", "client-prev", profiles=[*PROFILES, "rollout"])
    env.baseline()
    log("flags at baseline, toxics cleared, incidents reset")
    if wipe:
        wipe_sources()
        log("Vitals, BugDrop and ride data wiped")
    STATE.unlink(missing_ok=True)


def wipe_sources() -> None:
    """Empty the discovery sources and ride data, and put the driver fleet back where it was seeded.

    Scenarios move drivers (gps_loss nulls their coordinates through an endpoint only BUG-004's release has),
    and nothing else restores them: after a few sweeps no San Francisco driver near the Ferry Building had a
    position left, so BUG-020's riders were matched 5 km away and never saw the in-trip ETA. Dispatch seeds a
    deterministic fleet at startup when the table is empty, so deleting the drivers and restarting it restores
    exactly the original positions.
    """
    sql = {
        "vitals": "TRUNCATE events, groups, issues, sessions",
        "bugdrop": "TRUNCATE reports",
        "miniride": "TRUNCATE rides; DELETE FROM drivers",
    }
    for db, stmt in sql.items():
        subprocess.run(
            ["docker", "exec", "debugassist-postgres-1", "psql", "-U", "debugassist", "-d", db, "-qc", stmt],
            check=False,
            capture_output=True,
        )
    reseed_drivers()


def reseed_drivers(timeout_s: float = 90) -> None:
    """Restart dispatch so it re-seeds its fleet, and wait until it answers again."""
    running = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", "debugassist-dispatch-1"],
        capture_output=True,
        text=True,
    )
    if running.stdout.strip() != "true":
        return  # dispatch is not running (no target profile): nothing to restore
    compose("restart", "dispatch")  # through compose, so its view of the container stays consistent
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if httpx.get("http://localhost:8001/healthz", timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)


def hidden_test_paths(bug: Bug) -> list[tuple[Path, str, str]]:
    return [(bug.path(h.src), h.repo, h.dest) for h in bug.ground_truth.hidden_tests]
