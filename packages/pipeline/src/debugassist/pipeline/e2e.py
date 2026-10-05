"""E2E tier of the validation ladder (D14): Playwright against a build of the worktree, with the user's
captured environment emulated (network profile, CPU throttling, visibility, flag variants).

The agent never runs anything here itself. It writes the spec; the pipeline builds the worktree in the
network-less sandbox, then runs the spec in the official Playwright image on an *internal* Docker
network that only reaches the MiniRide backends the client talks to (no internet). Builds are cached
by the source state, so a reproduction is built once on the release and once per fix.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
from typing import Any, cast

from debugassist.integrations.sandbox import CommandResult, Sandbox
from debugassist.llm.workspace_tools import changed_files, is_test_path

NETWORK = "debugassist-e2e"
COMPOSE_PROJECT = "debugassist"
SERVE_PORT = 8080
HELPER_PATH = "e2e/support/emulate.ts"
WORK_DIR = ".da-e2e"  # git-excluded scratch inside the worktree (builds, server, results)
# How the client under test reaches the stack from inside the E2E network (overridable in the repo's
# pipeline.yaml `e2e.build_env`). Telemetry endpoints are left empty so test runs add no noise.
BUILD_ENV = {
    "VITE_GATEWAY_URL": "http://gateway:4000",
    "VITE_UNLEASH_URL": "http://unleash:4242/api/frontend",
    "VITE_UNLEASH_CLIENT_KEY": "default:development.unleash-insecure-frontend-api-token",
    "VITE_OTLP_TRACES_URL": "",
    "VITE_VITALS_URL": "",
    "VITE_BUGDROP_URL": "",
}
RUN_ENV = {"E2E_BASE_URL": f"http://localhost:{SERVE_PORT}", "E2E_GATEWAY_URL": "http://gateway:4000"}

EMULATE_TS = """\
import type { BrowserContext, Page } from "@playwright/test";

/** A captured network profile (Chromium only): latency per request, bandwidth and packet loss. */
export interface NetworkProfile {
  latencyMs: number;
  downloadKbps: number;
  uploadKbps: number;
  lossPct?: number;
}

/** Emulate the user's network for every request the page makes. */
export async function emulateNetwork(page: Page, profile: NetworkProfile): Promise<void> {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.emulateNetworkConditions", {
    offline: false,
    latency: profile.latencyMs,
    downloadThroughput: (profile.downloadKbps * 1000) / 8,
    uploadThroughput: (profile.uploadKbps * 1000) / 8,
    packetLoss: profile.lossPct ?? 0,
  });
}

/** Slow the CPU down by `rate` (4 = a mid-range phone). */
export async function throttleCpu(page: Page, rate: number): Promise<void> {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setCPUThrottlingRate", { rate });
}

/** Make `document.visibilityState` controllable; call before `page.goto`. */
export async function installVisibility(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const w = window as unknown as { __hidden: boolean };
    w.__hidden = false;
    Object.defineProperty(document, "hidden", { configurable: true, get: () => w.__hidden });
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => (w.__hidden ? "hidden" : "visible"),
    });
  });
}

/** Background (hidden=true) or foreground the app, firing `visibilitychange` like a real tab switch. */
export async function setHidden(page: Page, hidden: boolean): Promise<void> {
  await page.evaluate((h) => {
    (window as unknown as { __hidden: boolean }).__hidden = h;
    document.dispatchEvent(new Event("visibilitychange"));
  }, hidden);
}

/** Serve these flag values instead of the live flag service (the user's exposure). */
export async function setFlags(context: BrowserContext, flags: Record<string, boolean>): Promise<void> {
  await context.route("**/api/frontend**", (route) =>
    route.fulfill({
      json: {
        toggles: Object.entries(flags).map(([name, enabled]) => ({
          name,
          enabled,
          variant: { name: "disabled", enabled: false },
          impressionData: false,
        })),
      },
    }),
  );
}

/** Total main-thread script time so far, in seconds (CDP Performance metrics). */
export async function scriptSeconds(page: Page): Promise<number> {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Performance.enable");
  const { metrics } = await cdp.send("Performance.getMetrics");
  return metrics.find((m) => m.name === "ScriptDuration")?.value ?? 0;
}
"""

SERVE_MJS = """\
// Static server with SPA fallback for the build under test.
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";

const [root, port] = process.argv.slice(2);
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
  ".png": "image/png", ".json": "application/json", ".webmanifest": "application/manifest+json", ".map": "application/json" };
createServer((req, res) => {
  const url = new URL(req.url ?? "/", "http://x");
  if (url.pathname === "/healthz") return res.end("ok");
  let file = join(root, normalize(url.pathname).replace(/^([.][.][/\\\\])+/, ""));
  if (!existsSync(file) || statSync(file).isDirectory()) file = join(root, "index.html");
  res.writeHead(200, { "content-type": types[extname(file)] ?? "application/octet-stream" });
  createReadStream(file).pipe(res);
}).listen(Number(port), "0.0.0.0");
"""


def e2e_cmd(test_file: str, component: str) -> str:
    rel = test_file if component == "." else test_file.removeprefix(f"{component}/")
    return f"pnpm exec playwright test {rel}"


def is_e2e_cmd(cmd: str) -> bool:
    return cmd.startswith("pnpm exec playwright test ")


def _docker(*args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


def _containers(e2e_cfg: dict[str, Any]) -> dict[str, str]:
    """Backends the client talks to → their compose container names (the client itself is under test)."""
    services = [s for s in e2e_cfg.get("requires", []) if s != "client"]
    return {s: f"{COMPOSE_PROJECT}-{s}-1" for s in services}


def _playwright_version(sb: Sandbox, component: str) -> str | None:
    pkg = sb.worktree / component / "node_modules" / "@playwright" / "test" / "package.json"
    return json.loads(pkg.read_text())["version"] if pkg.is_file() else None


def image(sb: Sandbox, component: str) -> str | None:
    v = _playwright_version(sb, component)
    return f"mcr.microsoft.com/playwright:v{v}-noble" if v else None


def unavailable(sb: Sandbox, pipeline: dict[str, Any], component: str) -> str | None:
    """Why the E2E tier can't run here (None = it can)."""
    cfg = pipeline.get("e2e")
    if not isinstance(cfg, dict):
        return "the repository defines no e2e setup"
    img = image(sb, component)
    if img is None:
        return "@playwright/test is not installed in the component"
    if _docker("image", "inspect", img).returncode:
        return f"the Playwright image {img} is not available locally (docker pull {img})"
    for svc, name in _containers(cast_dict(cfg)).items():
        out = _docker("inspect", "-f", "{{.State.Running}}", name)
        if out.stdout.strip() != "true":
            return f"the {svc} service is not running (make up)"
    return None


def cast_dict(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def ensure_network(e2e_cfg: dict[str, Any]) -> None:
    """An internal network (no route out) with the required backends attached under their service names."""
    if _docker("network", "inspect", NETWORK).returncode:
        _docker("network", "create", "--internal", NETWORK)
    for svc, name in _containers(e2e_cfg).items():
        out = _docker("network", "connect", "--alias", svc, NETWORK, name)
        if out.returncode and "already exists" not in out.stderr and "already attached" not in out.stderr:
            raise RuntimeError(f"cannot attach {name} to {NETWORK}: {out.stderr.strip()}")


def write_helpers(sb: Sandbox, component: str) -> None:
    """The emulation helper ships with the test (a test path); the server is scratch."""
    root = sb.worktree / component
    helper = root / HELPER_PATH
    if not helper.exists():
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text(EMULATE_TS)
    work = root / WORK_DIR
    work.mkdir(exist_ok=True)
    (work / "serve.mjs").write_text(SERVE_MJS)


def _source_key(sb: Sandbox) -> str:
    """Builds depend only on non-test files: HEAD plus the diff of changed source files."""
    src = [f for f in changed_files(sb.diff("HEAD")) if not is_test_path(f)]
    diff = (
        subprocess.run(
            ["git", "diff", "HEAD", "--", *src], cwd=sb.worktree, capture_output=True, text=True, check=True
        ).stdout
        if src
        else ""
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=sb.worktree, capture_output=True, text=True, check=True
    ).stdout
    return hashlib.sha256((head + diff).encode()).hexdigest()[:12]


def build(sb: Sandbox, pipeline: dict[str, Any], component: str) -> tuple[str | None, CommandResult | None]:
    """Build the worktree's current source (cached). Returns (dist dir relative to the component, failure)."""
    env = {**BUILD_ENV, **cast_dict(cast_dict(pipeline.get("e2e")).get("build_env"))}
    dist = f"{WORK_DIR}/dist-{_source_key(sb)}"
    if (sb.worktree / component / dist / "index.html").is_file():
        return dist, None
    assigns = " ".join(f"{k}={shlex.quote(str(v))}" for k, v in env.items())
    res = sb.run(
        f"env {assigns} pnpm exec vite build --outDir {dist} --emptyOutDir --logLevel warn",
        workdir=component,
        timeout=600,
    )
    return (dist, None) if res.exit_code == 0 else (None, res)


def run(sb: Sandbox, pipeline: dict[str, Any], component: str, cmd: str, timeout: int = 600) -> CommandResult:
    """Build the current source, serve it and run one Playwright spec against the stack."""
    e2e_cfg = cast_dict(pipeline.get("e2e"))
    if why := unavailable(sb, pipeline, component):
        return CommandResult(cmd, 2, f"E2E tier unavailable: {why}")
    write_helpers(sb, component)
    dist, failure = build(sb, pipeline, component)
    if dist is None:
        assert failure
        return CommandResult(cmd, failure.exit_code, f"build failed:\n{failure.output[-3000:]}")
    ensure_network(e2e_cfg)
    spec = cmd.removeprefix("pnpm exec playwright test ").strip()
    script = (
        f"node {WORK_DIR}/serve.mjs {dist} {SERVE_PORT} & sleep 1; "
        f"node node_modules/@playwright/test/cli.js test {shlex.quote(spec)} --reporter=line "
        f"--output={WORK_DIR}/test-results"
    )
    img = image(sb, component)
    assert img
    env_args = [a for k, v in {**RUN_ENV, "CI": "1", "HOME": "/tmp"}.items() for a in ("-e", f"{k}={v}")]
    docker = [
        "docker", "run", "--rm", "--network", NETWORK, "--ipc=host", "--memory", "3g", "--cpus", "2",
        "-v", f"{sb.worktree}:/work", "-w", f"/work/{component}".rstrip("/."), *env_args,
        img, "sh", "-c", script,
    ]  # fmt: skip
    try:
        p = subprocess.run(docker, capture_output=True, text=True, timeout=timeout)
        return CommandResult(cmd, p.returncode, clean_output(p.stdout + p.stderr)[-12000:])
    except subprocess.TimeoutExpired:
        return CommandResult(cmd, 124, f"timed out after {timeout}s")


def captured_env(report: dict[str, Any], event: dict[str, Any], evidence: list[Any]) -> dict[str, Any]:
    """The user's environment as far as the report, the crash event and the evidence show it — what an
    E2E test emulates (flag exposures matter most: a flag at 0% today still decides what the user ran)."""
    env: dict[str, Any] = {}
    net = cast_dict(report.get("network"))
    if net:
        rtt = float(net.get("rtt") or 0)
        down = float(net.get("downlink") or 0)
        env["network"] = {
            "latencyMs": int(rtt),
            "downloadKbps": int(down * 1000),
            "uploadKbps": int(down * 1000),  # not captured by the browser; assume symmetric
            "effectiveType": net.get("effectiveType"),
            "source": "navigator.connection at report time",
        }
    for key in ("device", "city", "route", "flags"):
        value = report.get(key) or event.get(key)
        if value:
            env[key] = value
    if event.get("culprit") and "route" not in env:
        env["route"] = event["culprit"]
    for e in evidence:
        data = cast_dict(getattr(e, "data", None))
        if data.get("kind") == "ui_state_timeline" or "visibility" in json.dumps(data, default=str)[:4000]:
            env.setdefault("visibility_evidence", getattr(e, "summary", ""))
            break
    return env


NOISE = ("attachment #", "Usage:", "npx playwright show-trace", "Error Context:", f"{WORK_DIR}/test-results/")


def clean_output(text: str) -> str:
    """Drop Playwright's attachment listings (traces, videos, screenshots) so the error stays visible."""
    keep = [
        line
        for line in text.splitlines()
        if (not any(n in line for n in NOISE) and not set(line.strip()) <= set("─ ")) or not line.strip()
    ]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(keep))


def helper_doc() -> str:
    return (
        f"`{HELPER_PATH}` (already in the worktree) exports emulateNetwork(page, {{latencyMs, downloadKbps, "
        "uploadKbps, lossPct}}), throttleCpu(page, rate), installVisibility(page) + setHidden(page, bool), "
        "setFlags(context, {flag: bool}) and scriptSeconds(page). The spec runs against a fresh build of the "
        "worktree; `baseURL` is set and the gateway is at process.env.E2E_GATEWAY_URL (http://gateway:4000)."
    )


__all__ = ["captured_env", "e2e_cmd", "helper_doc", "is_e2e_cmd", "run", "unavailable", "write_helpers"]
