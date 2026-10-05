"""Packaging and launching (SPEC §7): a PEX per agent type (built in a Linux container for the runtime
platform) uploaded to MinIO, a runtime image per type, and `run_in_container` — the same command a worker
runs for a queued issue.

Inside the runtime container the pipeline still drives its sandbox and E2E containers through the host's
Docker socket, so the checkout is mounted at the same absolute path as on the host. The container joins
the compose network and reaches the stack by service name; links shown to people keep localhost.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import httpx

from debugassist.core.policy import ROOT
from debugassist.harness import agent_types

DIST = ROOT / ".data" / "dist"
NETWORK = "debugassist_default"
BUILD_IMAGE = "python:3.13-slim"
BUCKET = "debugassist-artifacts"
# The stack by compose service name (container ports), for code inside the runtime container.
SERVICE_ENV = {
    "VITALS_URL": "http://vitals:8100",
    "BUGDROP_URL": "http://bugdrop:8200",
    "INCIDENTS_URL": "http://incidents:8300",
    "UNLEASH_URL": "http://unleash:4242",
    "LOKI_URL": "http://loki:3100",
    "JAEGER_URL": "http://jaeger:16686",
    "PROMETHEUS_URL": "http://prometheus:9090",
}
APPS = {
    "miniride-client": "miniride-client",
    "gateway": "miniride-services",
    "dispatch": "miniride-services",
    "payments": "miniride-services",
}


def _sh(cmd: list[str], *, timeout: int = 1800) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=ROOT)
    if p.returncode:
        raise RuntimeError(f"{' '.join(cmd[:4])} … failed:\n{(p.stdout + p.stderr)[-3000:]}")
    return p.stdout


def git_sha() -> str:
    """The commit a build came from; "-dirty" when the checkout had uncommitted changes."""
    sha = _sh(["git", "rev-parse", "--short", "HEAD"]).strip()
    dirty = _sh(
        ["git", "status", "--porcelain", "--", "packages", "sources", "configs", "marketplace"]
    ).strip()
    return f"{sha}-dirty" if dirty else sha


def build_pex(agent_type: str) -> Path:
    """Build .data/dist/debugassist-<type>.pex for linux (the runtime image's platform) from the locked
    workspace: dependencies from uv.lock, workspace packages from their source directories."""
    agent_types.load(agent_type)
    DIST.mkdir(parents=True, exist_ok=True)
    out = f"/out/debugassist-{agent_type}.pex"
    script = " && ".join(
        [
            "pip install -q --root-user-action=ignore pex==2.103.4 uv",
            # Only the Python workspace: targets/ and node_modules are not needed (and may hold unreadable
            # cloud-sync placeholders).
            "mkdir /build && cd /src && tar -cf - --exclude=.venv --exclude=__pycache__ --exclude=node_modules "
            "pyproject.toml uv.lock README.md LICENSE packages sources/*/service | tar -xf - -C /build && cd /build",
            "uv export --frozen --no-dev --no-emit-workspace --all-packages --no-hashes --no-header -o /tmp/req.txt",
            "pex -r /tmp/req.txt $(ls -d packages/*/ sources/*/service/) -c debugassist "
            f"--inject-env DA_AGENT_TYPE={agent_type} -o {out}",
        ]
    )
    _sh(
        [
            "docker", "run", "--rm", "-v", f"{ROOT}:/src:ro", "-v", f"{DIST}:/out",
            "--entrypoint", "sh", BUILD_IMAGE, "-c",
            f"apt-get update -qq && apt-get install -y -qq git >/dev/null && {script}",
        ],
        timeout=3600,
    )  # fmt: skip
    return DIST / f"debugassist-{agent_type}.pex"


def upload_pex(path: Path, agent_type: str, endpoint: str = "localhost:9000") -> str:
    """Store the PEX in MinIO under pex/<type>/<git sha>.pex (and latest.pex); returns the object key."""
    from minio import Minio

    client = Minio(
        endpoint,
        access_key=os.environ.get("MINIO_ROOT_USER", "debugassist"),
        secret_key=os.environ.get("MINIO_ROOT_PASSWORD", "debugassist-dev"),
        secure=False,
    )
    if not client.bucket_exists(BUCKET):
        client.make_bucket(BUCKET)
    key = f"pex/{agent_type}/{git_sha()}.pex"
    for k in (key, f"pex/{agent_type}/latest.pex"):
        client.fput_object(BUCKET, k, str(path), content_type="application/octet-stream")
    return f"s3://{BUCKET}/{key}"


def build_image(agent_type: str, pex: Path | None = None) -> str:
    t = agent_types.load(agent_type)
    pex = pex or DIST / f"debugassist-{agent_type}.pex"
    if not pex.is_file():
        raise FileNotFoundError(f"{pex} missing: build it first (make pex AGENT_TYPE={agent_type})")
    _sh(
        [
            "docker", "build", "-q", "-f", str(ROOT / "infra" / "runtime" / "Dockerfile"),
            "--build-arg", f"AGENT_TYPE={agent_type}", "--build-arg", f"PEX={pex.relative_to(DIST)}",
            "-t", t.runtime_image, "-t", f"{t.runtime_image}:{git_sha()}", str(DIST),
        ]
    )  # fmt: skip
    return t.runtime_image


def peek(issue_ref: str, vitals_url: str = "http://localhost:8100") -> dict[str, Any]:
    """Enough about an issue to pick its agent type before the run: source, kind, repo."""
    if issue_ref.upper().startswith("BD-"):
        return {
            "source": "bugdrop",
            "kind": "bug_report",
            "repo": "miniride-client",
            "language": "typescript",
        }
    i = httpx.get(f"{vitals_url}/api/issues/{issue_ref}", timeout=10).raise_for_status().json()
    repo = APPS.get(str(i.get("app")), "miniride-client")
    return {"source": "vitals", "kind": i.get("kind"), "repo": repo, "language": None}


def container_command(agent_type: str, issue_ref: str, run_args: list[str]) -> list[str]:
    t = agent_types.load(agent_type)
    # The host's DA_* settings (e.g. DA_MODE_GITHUB=mock) win over the mounted .env inside the container.
    passthrough = {k: v for k, v in os.environ.items() if k.startswith("DA_")}
    values = {**SERVICE_ENV, "DEBUGASSIST_ROOT": str(ROOT), **passthrough}
    env = [a for k, v in values.items() for a in ("-e", f"{k}={v}")]
    return [
        "docker", "run", "--rm", "--network", NETWORK,
        "-v", "/var/run/docker.sock:/var/run/docker.sock",
        "-v", f"{ROOT}:{ROOT}", "-w", str(ROOT), *env,
        t.runtime_image, "run", "--agent-type", agent_type, "--issue", issue_ref, *run_args,
    ]  # fmt: skip


def run_in_container(agent_type: str, issue_ref: str, run_args: list[str], log: Path | None = None) -> int:
    cmd = container_command(agent_type, issue_ref, run_args)
    if log is None:
        return subprocess.run(cmd, check=False).returncode
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as f:
        return subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, check=False).returncode
