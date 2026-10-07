"""Capture proof screenshots of the running system into docs/screenshots/ (make screenshots).

    uv run --no-sync python scripts/screenshots.py stack       # MiniRide, Vitals, BugDrop, Jaeger, Unleash
    uv run --no-sync python scripts/screenshots.py run [ID]    # report, CLI summary, GitHub PR/diff/checks, Jira
    uv run --no-sync python scripts/screenshots.py jira-login  # once: sign in to Jira yourself in the window

The Jira login is yours: a visible browser opens, you sign in, and the session is kept in
.data/jira-auth.json (gitignored) so later captures can open the ticket. Nothing is typed for you.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import sys
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path
from typing import Any

import httpx
from playwright.async_api import Browser, Page, async_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"
MANIFEST = OUT / "manifest.json"
JIRA_AUTH = ROOT / ".data" / "jira-auth.json"
UNLEASH_DEV_LOGIN = ("admin", "unleash4all")  # Unleash's documented local default; local stack only


def richest_trace() -> tuple[str, list[str], int] | None:
    """The recent trace touching the most services (Jaeger v2 query API v3: one JSON document per trace)."""
    now = datetime.now(UTC)
    params = {
        "query.service_name": "gateway",
        "query.start_time_min": (now - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "query.start_time_max": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "query.search_depth": "300",
    }
    try:
        r = httpx.get("http://localhost:16686/api/v3/traces", params=params, timeout=20)
    except httpx.HTTPError:
        return None
    traces: dict[str, tuple[set[str], list[int]]] = {}  # a streamed chunk may hold several traces
    for line in r.text.splitlines():
        if not line.strip():
            continue
        for rs in json.loads(line).get("result", {}).get("resourceSpans", []):
            attrs = {a["key"]: a["value"].get("stringValue") for a in rs["resource"].get("attributes", [])}
            for ss in rs.get("scopeSpans", []):
                for sp in ss.get("spans", []):
                    services, count = traces.setdefault(sp["traceId"], (set(), [0]))
                    services.add(str(attrs.get("service.name")))
                    count[0] += 1
    ranked = sorted(((len(sv), c[0], tid, sorted(sv)) for tid, (sv, c) in traces.items()), reverse=True)
    best = ranked[0] if ranked and ranked[0][0] >= 2 else None
    return (best[2], best[3], best[1]) if best else None


def latest_run_id() -> str | None:
    runs = sorted((ROOT / ".data" / "runs").glob("*/state.json"), key=lambda p: p.stat().st_mtime)
    return runs[-1].parent.name if runs else None


async def shot(
    page: Page, url: str, name: str, *, wait_for: str | None = None, full: bool = True, delay_ms: int = 800
) -> str:
    await page.goto(url, wait_until="domcontentloaded")
    if wait_for:
        with contextlib.suppress(Exception):  # screenshot whatever is there
            await page.locator(wait_for).first.wait_for(timeout=15_000)
    await page.wait_for_timeout(delay_ms)
    path = OUT / f"{name}.png"
    await page.screenshot(path=str(path), full_page=full)
    return path.name


def _manifest() -> dict[str, Any]:
    return json.loads(MANIFEST.read_text()) if MANIFEST.is_file() else {"shots": {}}


def _save(entries: list[tuple[str, str, str]], **meta: Any) -> None:
    m = _manifest()
    for name, section, caption in entries:
        m["shots"][name] = {
            "section": section,
            "caption": caption,
            "at": f"{datetime.now(UTC):%Y-%m-%d %H:%M} UTC",
        }
    m.update(meta)
    MANIFEST.write_text(json.dumps(m, indent=2) + "\n")
    _readme(m)


async def stack(browser: Browser, pw: Any) -> list[tuple[str, str, str]]:
    taken: list[tuple[str, str, str]] = []
    async with httpx.AsyncClient(timeout=10) as http:
        issues = (await http.get("http://localhost:8100/api/issues")).json()
        reports = (await http.get("http://localhost:8200/api/reports")).json()
    desktop = await browser.new_page(viewport={"width": 1400, "height": 900})
    device = {k: v for k, v in pw.devices["Pixel 7"].items() if k != "default_browser_type"}
    phone = await (await browser.new_context(**device)).new_page()
    s = "1 · The system under test"
    taken.append(
        (
            await shot(
                phone, "http://localhost:8080/", "01-miniride-home", wait_for="text=Where to?", full=False
            ),
            s,
            "MiniRide, the rider web app DebugAssist debugs (React PWA), with the in-app 'Report a bug' button",
        )
    )
    if trace := richest_trace():
        tid, services, spans = trace
        taken.append(
            (
                await shot(
                    desktop,
                    f"http://localhost:16686/trace/{tid}",
                    "02-jaeger-trace",
                    wait_for="text=Service & Operation",
                    full=False,
                    delay_ms=2500,
                ),
                s,
                f"Jaeger: one rider request traced end to end across {', '.join(services)} ({spans} spans, OpenTelemetry)",
            )
        )
    s = "2 · Where bugs come from"
    taken.append(
        (
            await shot(desktop, "http://localhost:8100/", "03-vitals-issues", wait_for="table"),
            s,
            "Vitals (crash analytics): crashes grouped into issues by fingerprint",
        )
    )
    if issues:
        taken.append(
            (
                await shot(
                    desktop,
                    f"http://localhost:8100/issues/{issues[0]['id']}",
                    "04-vitals-issue",
                    wait_for="pre",
                ),
                s,
                f"Vitals {issues[0]['id']}: symbolicated stack trace, breadcrumbs, flag exposure and affected versions",
            )
        )
    taken.append(
        (
            await shot(desktop, "http://localhost:8200/", "05-bugdrop-reports", wait_for="table"),
            s,
            "BugDrop: bug reports filed from inside the app",
        )
    )
    if reports:
        taken.append(
            (
                await shot(
                    desktop,
                    f"http://localhost:8200/reports/{reports[0]['id']}?kind=analytics",
                    "06-bugdrop-report",
                    wait_for="blockquote",
                ),
                s,
                f"BugDrop {reports[0]['id']}: the user's description, screenshots, UI-state timeline and logs",
            )
        )
    await desktop.goto("http://localhost:4242/login", wait_until="domcontentloaded")
    try:
        await desktop.get_by_label("Email").fill(UNLEASH_DEV_LOGIN[0], timeout=8_000)
        await desktop.get_by_label("Password").fill(UNLEASH_DEV_LOGIN[1])
        await desktop.get_by_role("button", name="Sign in").click()
        await desktop.wait_for_timeout(2_000)
        await desktop.goto(
            "http://localhost:4242/projects/default/features/notif_router_v2", wait_until="domcontentloaded"
        )
        await desktop.get_by_text("development", exact=True).first.click(
            timeout=10_000
        )  # expand the strategy
        await desktop.wait_for_timeout(1_500)
        tip = desktop.get_by_text("Ok, got it!")
        if await tip.count():
            await tip.first.click()
            await desktop.wait_for_timeout(500)
        await desktop.screenshot(path=str(OUT / "07-unleash-flag.png"), full_page=False)
        taken.append(
            (
                "07-unleash-flag.png",
                s,
                "Unleash: the notif_router_v2 feature flag on a 5% gradual rollout, the flag behind the crash",
            )
        )
    except Exception as exc:
        print(f"unleash screenshot skipped: {exc}", file=sys.stderr)
    return taken


def _terminal_html(run_id: str) -> str:
    from debugassist.pipeline.cli import _summary  # pyright: ignore[reportPrivateUsage]
    from debugassist.pipeline.state import RunState

    state = RunState.model_validate_json((ROOT / ".data" / "runs" / run_id / "state.json").read_text())
    buf = io.StringIO()
    with redirect_stdout(buf):
        _summary(state)
    cmd = f"# end-of-run summary printed by `debugassist run {state.issue_ref} --llm live` (re-printed from the run state)"
    steps = "\n".join(f"  ▶ {n}" for n in state.timings_ms)
    text = f"{cmd}\nrun {run_id} ({state.mode}, LLM {state.llm_mode}); artifacts in .data/runs/{run_id}/\n{steps}\n{buf.getvalue()}"
    return (
        "<!doctype html><meta charset=utf-8><style>body{margin:0;background:#0d1117;padding:22px}"
        ".w{background:#161b22;border:1px solid #30363d;border-radius:10px;max-width:1240px;box-shadow:0 10px 40px #0008}"
        ".t{height:34px;display:flex;gap:8px;align-items:center;padding:0 14px;border-bottom:1px solid #30363d}"
        ".t i{width:12px;height:12px;border-radius:50%;display:block}pre{margin:0;padding:18px 20px;color:#e6edf3;"
        "font:14px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap}</style>"
        "<div class=w><div class=t><i style=background:#ff5f57></i><i style=background:#febc2e></i><i style=background:#28c840></i></div>"
        f"<pre>{escape(text)}</pre></div>"
    )


async def run(browser: Browser, run_id: str) -> list[tuple[str, str, str]]:
    from debugassist.pipeline.report import render

    taken: list[tuple[str, str, str]] = []
    state = json.loads((ROOT / ".data" / "runs" / run_id / "state.json").read_text())
    report = ROOT / ".data" / "runs" / run_id / "report.html"
    report.write_text(render(run_id))
    term = ROOT / ".data" / "runs" / run_id / "terminal.html"
    term.write_text(_terminal_html(run_id))
    page = await browser.new_page(viewport={"width": 1400, "height": 900})
    s = "3 · One command, end to end"
    await page.goto(term.as_uri())
    await page.locator(".w").screenshot(path=str(OUT / "08-cli-run.png"))
    taken.append(
        (
            "08-cli-run.png",
            s,
            f"`debugassist run {state['issue_ref']}`: triage → root cause → mitigation → reproduce + fix → validate → PR",
        )
    )
    s = "4 · What happened inside the run"
    taken.append(
        (
            await shot(page, report.as_uri(), "09-run-report-overview", full=False, delay_ms=300),
            s,
            "Run report: outcome, validation, time, LLM usage, and the Clef decision count",
        )
    )
    taken.append(
        (
            await shot(page, report.as_uri(), "10-run-report-full", delay_ms=300),
            s,
            "Full run report: Clef decisions, evidence-backed root cause, mitigation statistics, the diff, the validation proof, the write audit and agent tool calls",
        )
    )
    pr = state.get("pr") or {}
    if str(pr.get("url", "")).startswith("https://github.com/"):
        s = "5 · The pull request it opened"
        url = str(pr["url"])
        taken.append(
            (
                await shot(page, url, "11-github-pr", wait_for=".markdown-body", delay_ms=1500),
                s,
                f"GitHub pull request opened by DebugAssist: root cause, evidence, validation and links ({url})",
            )
        )
        taken.append(
            (
                await shot(
                    page, url + "/files", "12-github-pr-diff", wait_for="text=Files changed", delay_ms=2500
                ),
                s,
                "The fix (one line in src/notifications/router.ts) and the regression test it ships with",
            )
        )
        taken.append(
            (
                await shot(page, url + "/checks", "13-github-pr-checks", delay_ms=2500),
                s,
                "The target repository's own CI on the PR",
            )
        )
    t = state.get("triage") or {}
    if JIRA_AUTH.is_file() and str(t.get("jira_url", "")).startswith("https://"):
        ctx = await browser.new_context(
            storage_state=str(JIRA_AUTH), viewport={"width": 1400, "height": 1000}
        )
        jp = await ctx.new_page()
        taken.append(
            (
                await shot(jp, str(t["jira_url"]), "14-jira-ticket", delay_ms=5000),
                "6 · The ticket it filed",
                f"Jira {t['jira_key']}: filed at triage, root cause commented, PR linked, moved to In Review",
            )
        )
    return taken


async def jira_login(pw: Any) -> None:
    from debugassist.core.settings import get_settings

    base = get_settings().jira_base_url
    if not base:
        raise SystemExit("JIRA_BASE_URL is not set")
    browser = await pw.chromium.launch(headless=False)
    ctx = await browser.new_context()
    page = await ctx.new_page()
    await page.goto(base)
    print("Sign in to Jira in the browser window. Waiting up to 5 minutes…")
    await page.wait_for_url(f"{base.rstrip('/')}/**", timeout=300_000)
    await page.wait_for_selector("[data-testid*='app-navigation'], nav", timeout=300_000)
    JIRA_AUTH.parent.mkdir(exist_ok=True)
    await ctx.storage_state(path=str(JIRA_AUTH))
    print(f"saved session to {JIRA_AUTH.relative_to(ROOT)} (gitignored)")
    await browser.close()


SECTIONS_INTRO = {
    "1 · The system under test": "A small ride-hailing system built for this project: a React web client plus "
    "gateway (Node/GraphQL), dispatch (Python/FastAPI) and payments (Go), all instrumented with OpenTelemetry.",
    "2 · Where bugs come from": "Crashes flow into Vitals, user bug reports into BugDrop. Release 1.6.1 shipped a "
    "real-looking regression behind a 5% feature-flag rollout; tapping a push notification right after launch crashes.",
    "3 · One command, end to end": "No human in the loop: DebugAssist picks up the Vitals issue and finishes with a "
    "validated pull request and an updated ticket.",
    "4 · What happened inside the run": "Every number below comes from the run's own artifacts: state, the Clef "
    "decision ledger and the audit log of write actions.",
    "5 · The pull request it opened": "A bot branch on the target repo, opened against the release branch.",
    "6 · The ticket it filed": "",
}


def _readme(m: dict[str, Any]) -> None:
    shots: dict[str, Any] = m["shots"]
    lines = [
        "# DebugAssist screenshots",
        "",
        "Proof from live runs against the local MiniRide stack, captured with `make screenshots` "
        "(`scripts/screenshots.py`). The LLM, Clef, GitHub and Jira calls in the run shown were live, not mocked. "
        "The riders are simulated: all MiniRide traffic, the crashes and the BugDrop report come from the "
        "project's Playwright rider fleet (`packages/simulator`), using the real app UI.",
        "",
    ]
    if m.get("run_id"):
        lines += [
            f"Run shown: `{m['run_id']}` · regenerate its report with `debugassist report {m['run_id']}`.",
            "",
        ]
    for section in sorted({v["section"] for v in shots.values()}):
        lines += [f"## {section}", ""]
        if SECTIONS_INTRO.get(section):
            lines += [SECTIONS_INTRO[section], ""]
        for name, v in sorted(shots.items()):
            if v["section"] == section:
                lines += [f"**{v['caption']}** · captured {v['at']}", "", f"![{v['caption']}]({name})", ""]
    if not any(n.startswith("14-") for n in shots):
        lines += [
            "## Jira",
            "",
            "Run `uv run --no-sync python scripts/screenshots.py jira-login` once and sign in, "
            "then `make screenshots` captures the ticket too.",
            "",
        ]
    lines += ["---", "Open-source project; not affiliated with Uber or Cloudflare."]
    (OUT / "README.md").write_text("\n".join(lines) + "\n")


async def dashboard(browser: Browser, run_id: str | None) -> list[tuple[str, str, str]]:
    """The dashboard (`make dashboard` on :3000) at 1600 px wide; `run_id` picks the run shown as a graph."""
    page = await browser.new_page(
        viewport={"width": 1440, "height": 900}, device_scale_factor=1600 / 1440, color_scheme="dark"
    )
    s = "5 · The dashboard"
    pages = [
        (
            "19-dashboard-inbox",
            "/",
            "Inbox: Vitals crashes and BugDrop reports with their triage and latest run",
        ),
        ("20-dashboard-runs", "/runs", "Runs: root-cause category and location, outcome, cost and time"),
        (
            "21-dashboard-run-graph",
            f"/runs/{run_id}" if run_id else "/runs",
            "A run as a graph: steps, subagents and every agent call",
        ),
        (
            "22-dashboard-metrics",
            "/metrics",
            "Metrics: live and scripted runs kept apart; decision quality per template",
        ),
        (
            "23-dashboard-marketplace",
            "/marketplace",
            "Marketplace: plugins, skills and proposed skill updates",
        ),
    ]
    taken: list[tuple[str, str, str]] = []
    for name, path, caption in pages:
        await page.goto(f"http://localhost:3000{path}", wait_until="networkidle")
        await page.add_style_tag(content="nextjs-portal{display:none!important}")  # Next.js dev badge
        await page.wait_for_timeout(2500)
        await page.screenshot(path=str(OUT / f"{name}.png"))
        taken.append((f"{name}.png", s, caption))
    return taken


async def main(argv: list[str]) -> None:
    what = argv[0] if argv else "all"
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        if what == "jira-login":
            await jira_login(pw)
            return
        browser = await pw.chromium.launch()
        meta: dict[str, Any] = {}
        taken: list[tuple[str, str, str]] = []
        if what in ("stack", "all"):
            taken += await stack(browser, pw)
        if what in ("run", "all"):
            run_id = argv[1] if len(argv) > 1 else latest_run_id()
            if run_id:
                taken += await run(browser, run_id)
                meta["run_id"] = run_id
        if what == "dashboard":
            taken += await dashboard(browser, argv[1] if len(argv) > 1 else None)
        await browser.close()
    _save(taken, **meta)
    print("\n".join(f"docs/screenshots/{n}" for n, _, _ in taken))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
