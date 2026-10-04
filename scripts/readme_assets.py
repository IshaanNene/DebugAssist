"""Build the README visuals into docs/assets/ (make readme-assets).

    uv run --no-sync python scripts/readme_assets.py [svg|gif|all]

* hero.svg, architecture.svg, stack.svg — hand-laid SVG with brand logos embedded as vector paths
  (GitHub does not load external images inside SVGs). Icons are vendored in docs/assets/icons/:
  Simple Icons (CC0) and LobeHub icons (MIT); the Unleash mark is Unleash's own PNG. Trademarks
  belong to their owners and indicate integrations only.
* demo.gif — a storyboard from the real screenshots in docs/screenshots/ and a terminal replay of
  a real keyless run (`debugassist run … --llm mock`, re-printed from its state), encoded by ffmpeg.
"""

from __future__ import annotations

import asyncio
import base64
import io
import re
import shutil
import sys
import tempfile
from contextlib import redirect_stdout
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets"
ICONS = ASSETS / "icons"
SHOTS = ROOT / "docs" / "screenshots"
FONT = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "'JetBrains Mono', SFMono-Regular, Menlo, Consolas, monospace"

# Brand colours (Simple Icons metadata; Groq/Playwright/Slack from their brand pages).
BRAND = {
    "openrouter": "94A3B8",
    "redis": "FF4438",
    "postgresql": "4169E1",
    "docker": "2496ED",
    "cloudflare": "F38020",
    "github": "181717",
    "jira": "0052CC",
    "opentelemetry": "F5A800",
    "jaeger": "66CFE3",
    "prometheus": "E6522C",
    "grafana": "F46800",
    "minio": "C72E49",
    "langchain": "7FC8FF",
    "playwright": "2EAD33",
    "react": "61DAFB",
    "python": "3776AB",
    "go": "00ADD8",
    "nodedotjs": "5FA04E",
    "typescript": "3178C6",
    "fastapi": "009688",
    "graphql": "E10098",
    "slack": "E01E5A",
    "sqlite": "0F80CC",
    "uv": "DE5FE9",
    "pydantic": "E92063",
    "modelcontextprotocol": "E6EDF3",
    "lobe-groq": "F55036",
    "lobe-langgraph": "E6EDF3",
    "lobe-nvidia": "76B900",
    "lobe-openai": "E6EDF3",
}

BG, CARD, LINE, INK, MUTE = "#0B0F17", "#121826", "#263042", "#E6EDF3", "#8B98AD"
ACCENT, ACCENT2, OK = "#7C5CFF", "#22D3EE", "#34D399"


def _readable(hex6: str) -> str:
    """Lighten brand colours that would vanish on the dark background."""
    r, g, b = (int(hex6[i : i + 2], 16) for i in (0, 2, 4))
    lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    if lum >= 0.32:
        return f"#{hex6}"
    t = 0.55 if lum < 0.15 else 0.35
    r, g, b = (round(c + (255 - c) * t) for c in (r, g, b))
    return f"#{r:02X}{g:02X}{b:02X}"


def logo(slug: str, x: float, y: float, size: float, color: str | None = None) -> str:
    """An icon as inline vector paths (or an embedded PNG), placed with its top-left at (x, y)."""
    png = ICONS / f"{slug}.png"
    if png.is_file():
        data = base64.b64encode(png.read_bytes()).decode()
        return f'<image x="{x}" y="{y}" width="{size}" height="{size}" href="data:image/png;base64,{data}"/>'
    svg = (ICONS / f"{slug}.svg").read_text()
    vb = re.search(r'viewBox="([\d.\s-]+)"', svg)
    w = float(vb.group(1).split()[2]) if vb else 24.0
    inner = re.sub(r"<title>.*?</title>", "", svg.split(">", 1)[1].rsplit("</svg>", 1)[0], flags=re.S)
    fill = color or _readable(BRAND.get(slug, "E6EDF3"))
    return f'<g transform="translate({x} {y}) scale({size / w:.4f})" fill="{fill}">{inner}</g>'


def text(
    x: float,
    y: float,
    s: str,
    size: int = 14,
    color: str = INK,
    weight: int = 500,
    anchor: str = "start",
    mono: bool = False,
) -> str:
    fam = MONO if mono else FONT
    return f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}">{escape(s)}</text>'


def card(
    x: float, y: float, w: float, h: float, title: str | None = None, accent: str = ACCENT, r: int = 16
) -> str:
    out = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{CARD}" stroke="{LINE}"/>'
    if title:
        out += f'<rect x="{x}" y="{y}" width="4" height="{h}" rx="2" fill="{accent}" opacity=".9"/>'
        out += text(x + 18, y + 26, title.upper(), 11, MUTE, 700)
    return out


def pill(x: float, y: float, s: str, color: str = ACCENT, w: float | None = None) -> str:
    w = w or 14 + len(s) * 6.6
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="22" rx="11" fill="{color}" fill-opacity=".16" stroke="{color}" stroke-opacity=".5"/>'
        + text(x + w / 2, y + 15, s, 11, color, 600, "middle")
    )


def svg_doc(w: int, h: int, body: str, extra_css: str = "") -> str:
    css = (
        "@keyframes dash{to{stroke-dashoffset:-28}} .flow{stroke-dasharray:6 8;animation:dash 1.1s linear infinite}"
        "@keyframes pulse{0%,100%{opacity:.35}50%{opacity:1}} .pulse{animation:pulse 2.4s ease-in-out infinite}"
        + extra_css
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img">'
        f"<style>{css}</style>{body}</svg>\n"
    )


# --------------------------------------------------------------------------------------- hero


def hero() -> str:
    w, h = 1280, 380
    stages = ["Crash", "Triage", "Root cause", "Mitigate", "Reproduce", "Fix", "Validate", "Pull request"]
    xs = [120 + i * 148 for i in range(len(stages))]
    track_y = 268
    body = [
        "<defs>",
        f'<radialGradient id="g1" cx="18%" cy="10%" r="70%"><stop offset="0" stop-color="{ACCENT}" stop-opacity=".45"/><stop offset="1" stop-color="{BG}" stop-opacity="0"/></radialGradient>',
        f'<radialGradient id="g2" cx="88%" cy="95%" r="60%"><stop offset="0" stop-color="{ACCENT2}" stop-opacity=".30"/><stop offset="1" stop-color="{BG}" stop-opacity="0"/></radialGradient>',
        f'<linearGradient id="t" x1="0" x2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset=".55" stop-color="#C9BFFF"/><stop offset="1" stop-color="{ACCENT2}"/></linearGradient>',
        f'<linearGradient id="trk" x1="0" x2="1"><stop offset="0" stop-color="{ACCENT}"/><stop offset="1" stop-color="{ACCENT2}"/></linearGradient>',
        '<pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse"><path d="M32 0H0V32" fill="none" stroke="#FFFFFF" stroke-opacity=".045"/></pattern>',
        '<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="6"/></filter>',
        "</defs>",
        f'<rect width="{w}" height="{h}" rx="24" fill="{BG}"/>',
        f'<rect width="{w}" height="{h}" rx="24" fill="url(#grid)"/>',
        f'<rect width="{w}" height="{h}" rx="24" fill="url(#g1)"/><rect width="{w}" height="{h}" rx="24" fill="url(#g2)"/>',
        text(64, 108, "DebugAssist", 64, "url(#t)", 800),
        text(
            66,
            150,
            "From a crash report to an evidence-backed root cause and a validated pull request.",
            21,
            "#C3CCDA",
            500,
        ),
        pill(66, 176, "Clef decides", "#F38020", 112),
        pill(188, 176, "LLMs reason and write code", ACCENT, 206),
        pill(404, 176, "Deterministic code acts", OK, 176),
        f'<line x1="{xs[0]}" y1="{track_y}" x2="{xs[-1]}" y2="{track_y}" stroke="{LINE}" stroke-width="3"/>',
        f'<line x1="{xs[0]}" y1="{track_y}" x2="{xs[-1]}" y2="{track_y}" stroke="url(#trk)" stroke-width="3" class="flow"/>',
    ]
    for i, (x, s) in enumerate(zip(xs, stages, strict=True)):
        body.append(
            f'<circle cx="{x}" cy="{track_y}" r="11" fill="{BG}" stroke="url(#trk)" stroke-width="3"/>'
        )
        body.append(
            f'<circle cx="{x}" cy="{track_y}" r="4" fill="{ACCENT2}" class="pulse" style="animation-delay:{i * 0.3:.1f}s"/>'
        )
        body.append(text(x, track_y + 36, s, 14, INK, 600, "middle"))
    body.append(
        f'<circle r="9" fill="{ACCENT2}" filter="url(#glow)"><animateMotion dur="6s" repeatCount="indefinite" path="M{xs[0]},{track_y} L{xs[-1]},{track_y}"/></circle>'
        f'<circle r="4" fill="#FFFFFF"><animateMotion dur="6s" repeatCount="indefinite" path="M{xs[0]},{track_y} L{xs[-1]},{track_y}"/></circle>'
    )
    # provider strip
    body.append(text(w - 64, 60, "DECISIONS", 10, MUTE, 700, "end"))
    label = "Cloudflare Clef on Workers AI"
    body.append(
        logo("cloudflare", w - 64 - len(label) * 7.1 - 38, 72, 28)
        + text(w - 64, 92, label, 13, INK, 600, "end")
    )
    body.append(text(w - 64, 132, "REASONING", 10, MUTE, 700, "end"))
    label = "GroqCloud · OpenRouter"
    lx = w - 64 - len(label) * 7.1 - 70
    body.append(
        logo("lobe-groq", lx, 146, 22)
        + logo("openrouter", lx + 30, 146, 22)
        + text(w - 64, 162, label, 13, INK, 600, "end")
    )
    return svg_doc(w, h, "".join(body))


# ------------------------------------------------------------------------------- architecture


def node(
    x: float, y: float, w: float, title: str, sub: str, decision: str | None = None, color: str = ACCENT
) -> str:
    h = 62
    out = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="#161E2E" stroke="{color}" stroke-opacity=".55"/>'
    out += text(x + 14, y + 26, title, 15, INK, 700) + text(x + 14, y + 46, sub, 11.5, MUTE, 500)
    if decision:
        cx, cy = x + w - 4, y - 2
        out += f'<rect x="{cx - 46}" y="{cy - 11}" width="54" height="22" rx="11" fill="#2A1A08" stroke="#F38020"/>'
        out += logo("cloudflare", cx - 41, cy - 7, 14) + text(cx - 23, cy + 4, decision, 10.5, "#FDBA74", 700)
    return out


def arrow(d: str, color: str = ACCENT2, flow: bool = True) -> str:
    cls = ' class="flow"' if flow else ""
    return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2" stroke-opacity=".85" marker-end="url(#ah)"{cls}/>'


def chip_logo(x: float, y: float, slug: str, label: str, w: float = 128) -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="34" rx="9" fill="#0F1522" stroke="{LINE}"/>'
        + logo(slug, x + 9, y + 7, 20)
        + text(x + 37, y + 22, label, 12.5, INK, 600)
    )


def chip_dot(x: float, y: float, color: str, label: str, w: float = 128) -> str:
    """A chip for our own services (no brand logo)."""
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="34" rx="9" fill="#0F1522" stroke="{LINE}"/>'
        f'<circle cx="{x + 19}" cy="{y + 17}" r="8" fill="{color}"/>'
        + text(x + 37, y + 22, label, 12.5, INK, 600)
    )


def architecture() -> str:
    w, h = 1440, 1024
    b: list[str] = [
        "<defs>",
        f'<marker id="ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="{ACCENT2}"/></marker>',
        '<pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse"><path d="M28 0H0V28" fill="none" stroke="#FFFFFF" stroke-opacity=".035"/></pattern>',
        "</defs>",
        f'<rect width="{w}" height="{h}" rx="24" fill="{BG}"/><rect width="{w}" height="{h}" rx="24" fill="url(#grid)"/>',
        text(40, 54, "How DebugAssist works", 26, INK, 800),
        text(
            40,
            80,
            "Signals in, a validated pull request out. The plan is fixed in code; Clef makes the calls; models reason; deterministic code acts.",
            14,
            MUTE,
        ),
    ]

    # 1 · Signals ------------------------------------------------------------------------------
    sx, sy, sw, sh = 32, 108, 330, 560
    b.append(card(sx, sy, sw, sh, "1 · Signals from the system under test", ACCENT2))
    b.append(text(sx + 18, sy + 58, "MiniRide (ride-hailing demo)", 15, INK, 700))
    b.append(text(sx + 18, sy + 78, "rider web app + three services", 12, MUTE))
    for i, (slug, lbl) in enumerate(
        [("react", "React PWA"), ("nodedotjs", "GraphQL gw"), ("fastapi", "Dispatch"), ("go", "Payments")]
    ):
        b.append(chip_logo(sx + 18 + (i % 2) * 150, sy + 92 + (i // 2) * 42, slug, lbl, 142))
    b.append(text(sx + 18, sy + 206, "Crashes and reports", 12, MUTE, 700))
    b.append(chip_dot(sx + 18, sy + 216, "#F43F5E", "Vitals", 142))
    b.append(chip_dot(sx + 168, sy + 216, "#F59E0B", "BugDrop", 142))
    b.append(text(sx + 18, sy + 276, "crash analytics · in-app bug reports", 11.5, MUTE))
    b.append(text(sx + 18, sy + 312, "Telemetry", 12, MUTE, 700))
    for i, (slug, lbl) in enumerate(
        [
            ("opentelemetry", "OTel Collector"),
            ("jaeger", "Jaeger"),
            ("grafana", "Loki"),
            ("prometheus", "Prometheus"),
        ]
    ):
        b.append(chip_logo(sx + 18 + (i % 2) * 150, sy + 322 + (i // 2) * 42, slug, lbl, 142))
    b.append(text(sx + 18, sy + 432, "Release controls", 12, MUTE, 700))
    b.append(chip_logo(sx + 18, sy + 442, "unleash", "Unleash flags", 142))
    b.append(chip_logo(sx + 168, sy + 442, "docker", "Toxiproxy", 142))
    b.append(text(sx + 18, sy + 506, "Riders simulated by a", 11.5, MUTE))
    b.append(
        logo("playwright", sx + 148, sy + 493, 16)
        + text(sx + 168, sy + 506, "Playwright fleet", 11.5, INK, 600)
    )
    b.append(text(sx + 18, sy + 526, "(devices, weak networks, backgrounding)", 11.5, MUTE))

    # 2 · Pipeline ------------------------------------------------------------------------------
    px, py, pw, ph = 392, 108, 640, 560
    b.append(card(px, py, pw, ph, "2 · The pipeline — a fixed LangGraph plan", ACCENT))
    b.append(logo("lobe-langgraph", px + pw - 40, py + 12, 22))
    cw = 186
    col = [px + 22, px + 22 + cw + 22, px + 22 + 2 * (cw + 22)]
    rows = [py + 60, py + 176, py + 292, py + 408]
    b.append(node(col[0], rows[0], cw, "Ingest", "Vitals issue / BugDrop report"))
    b.append(node(col[1], rows[0], cw, "Triage", "priority · owner · ticket", "D01"))
    b.append(node(col[2], rows[0], cw, "Context", "evidence from MCP servers"))
    b.append(node(col[2], rows[1], cw, "Root cause", "agent · claims cite evidence", "D05"))
    b.append(node(col[1], rows[1], cw, "Mitigate", "flag ↔ crash z-test", "D11"))
    b.append(node(col[0], rows[1], cw, "Reproduce", "a test that fails on release"))
    b.append(node(col[0], rows[2], cw, "Fix", "smallest change; test is frozen"))
    b.append(node(col[1], rows[2], cw, "Validate", "fails before · passes after", "D15", OK))
    b.append(node(col[2], rows[2], cw, "Ship gate", "repro + source change + proof", "D16"))
    b.append(node(col[2], rows[3], cw, "PR + ticket", "bot branch · draft if unsure", None, OK))
    b.append(node(col[1], rows[3], cw, "Report", "every step, decision, write", None, "#64748B"))
    for d in [
        f"M{col[0] + cw} {rows[0] + 31} H{col[1] - 4}",
        f"M{col[1] + cw} {rows[0] + 31} H{col[2] - 4}",
        f"M{col[2] + cw / 2} {rows[0] + 62} V{rows[1] - 4}",
        f"M{col[2]} {rows[1] + 31} H{col[1] + cw + 4}",
        f"M{col[1]} {rows[1] + 31} H{col[0] + cw + 4}",
        f"M{col[0] + cw / 2} {rows[1] + 62} V{rows[2] - 4}",
        f"M{col[0] + cw} {rows[2] + 31} H{col[1] - 4}",
        f"M{col[1] + cw} {rows[2] + 31} H{col[2] - 4}",
        f"M{col[2] + cw / 2} {rows[2] + 62} V{rows[3] - 4}",
        f"M{col[2]} {rows[3] + 31} H{col[1] + cw + 4}",
    ]:
        b.append(arrow(d))
    # retry loop validate -> fix
    b.append(
        f'<path d="M{col[1] + 40} {rows[2] + 62} C{col[1] + 40} {rows[2] + 100}, {col[0] + 120} {rows[2] + 100}, {col[0] + 120} {rows[2] + 66}" fill="none" stroke="{MUTE}" stroke-width="1.6" stroke-dasharray="4 5" marker-end="url(#ah)"/>'
    )
    b.append(text(col[0] + 150, rows[2] + 112, "retry ≤ 3 (D15)", 11, MUTE, 600))
    b.append(
        text(
            px + 22,
            py + ph - 52,
            "Checkpointed after every step · resumable from any step · mock mode needs no keys",
            12,
            MUTE,
        )
    )
    b.append(
        text(
            px + 22,
            py + ph - 30,
            "Pydantic models at every boundary · LLMs never pick the next step",
            12,
            MUTE,
        )
    )
    b.append(logo("pydantic", px + pw - 44, py + ph - 46, 20))

    # 3 · Reasoning ----------------------------------------------------------------------------
    rx, ry, rw = 1062, 108, 346
    b.append(card(rx, ry, rw, 196, "3 · Reasoning — OpenAI-compatible LLMs", "#F55036"))
    b.append(chip_logo(rx + 18, ry + 44, "lobe-groq", "GroqCloud", 150))
    b.append(chip_logo(rx + 178, ry + 44, "openrouter", "OpenRouter", 150))
    b.append(
        logo("lobe-openai", rx + 20, ry + 92, 16)
        + text(rx + 42, ry + 105, "gpt-oss-120b", 12.5, INK, 600, mono=True)
    )
    b.append(
        logo("lobe-nvidia", rx + 180, ry + 92, 16)
        + text(rx + 202, ry + 105, "Nemotron 3 Ultra", 12.5, INK, 600, mono=True)
    )
    b.append(chip_logo(rx + 18, ry + 120, "langchain", "LangChain agents", 150))
    b.append(chip_logo(rx + 178, ry + 120, "modelcontextprotocol", "MCP tools", 150))
    b.append(text(rx + 18, ry + 178, "token budgets · rejected-turn recovery · cassettes", 11.5, MUTE))

    b.append(card(rx, ry + 212, rw, 156, "MCP servers (evidence)", "#A78BFA"))
    for i, s in enumerate(["crash-analytics", "code-search", "git-history", "feature-flags"]):
        b.append(
            f'<rect x="{rx + 18 + (i % 2) * 160}" y="{ry + 256 + (i // 2) * 40}" width="150" height="30" rx="8" fill="#0F1522" stroke="{LINE}"/>'
        )
        b.append(
            text(
                rx + 93 + (i % 2) * 160, ry + 276 + (i // 2) * 40, s, 12, "#DDD6FE", 600, "middle", mono=True
            )
        )
    b.append(text(rx + 18, ry + 352, "every result carries an evidence id", 11.5, MUTE))

    b.append(card(rx, ry + 384, rw, 176, "Sandbox (where agents act)", "#2496ED"))
    b.append(chip_logo(rx + 18, ry + 428, "docker", "docker --network none", 200))
    b.append(chip_logo(rx + 18, ry + 470, "github", "git worktree per run", 200))
    b.append(text(rx + 18, ry + 528, "path · command · egress guards", 11.5, MUTE))
    b.append(text(rx + 18, ry + 546, "repo's own tests, lint and typecheck", 11.5, MUTE))

    # 4 · Decisions bar --------------------------------------------------------------------------
    dy = 690
    b.append(
        f'<rect x="32" y="{dy}" width="1376" height="84" rx="16" fill="#1A1208" stroke="#F38020" stroke-opacity=".55"/>'
    )
    b.append(logo("cloudflare", 54, dy + 22, 40))
    b.append(text(108, dy + 30, "Decisions: Cloudflare Clef on Workers AI", 17, "#FED7AA", 800))
    b.append(
        text(
            108,
            dy + 52,
            "Calibrated probabilities at every decision point (D01–D18) → policy bands: act · escalate · safe default.",
            12.5,
            "#FDBA74",
        )
    )
    b.append(
        text(
            108,
            dy + 70,
            "Every decision lands in a ledger. Clef never writes anything itself — the write-policy gate does.",
            12.5,
            "#FDBA74",
        )
    )
    for i, s in enumerate(["D01 triage", "D05 category", "D11 rollback", "D15 retry", "D16 ship"]):
        b.append(pill(1000 + (i % 3) * 134, dy + 14 + (i // 3) * 30, s, "#F38020", 124))
    b.append(arrow(f"M{px + pw / 2} {py + ph + 2} V{dy - 6}", "#F38020"))

    # 5 · Actions + storage ----------------------------------------------------------------------
    ay = 806
    b.append(arrow(f"M390 {dy + 86} V{ay - 6}", OK))
    b.append(text(402, dy + 104, "policy gate", 11, OK, 700))
    b.append(card(32, ay, 700, 186, "4 · Actions — policy-gated, audited, dry-run by default", OK))
    b.append(chip_logo(50, ay + 44, "github", "Pull request (bot branch)", 216))
    b.append(chip_logo(278, ay + 44, "jira", "Jira ticket", 140))
    b.append(chip_logo(430, ay + 44, "slack", "Slack (mock)", 140))
    b.append(chip_logo(582, ay + 44, "unleash", "Flag rollback", 138))
    b.append(
        text(
            50,
            ay + 112,
            "Pushes only to debugassist/* branches · every write goes through configs/policies/writes.yaml",
            12.5,
            MUTE,
        )
    )
    b.append(
        text(
            50,
            ay + 134,
            "and lands in an audit log · flag rollbacks need approval · ground truth never reaches the agent",
            12.5,
            MUTE,
        )
    )
    b.append(
        text(
            50,
            ay + 162,
            "Mock implementations for every integration — CI runs with no secrets.",
            12.5,
            INK,
            600,
        )
    )

    b.append(card(752, ay, 656, 186, "Data & infrastructure", "#64748B"))
    for i, (slug, lbl) in enumerate(
        [
            ("postgresql", "Postgres"),
            ("redis", "Redis"),
            ("minio", "MinIO"),
            ("sqlite", "SQLite ledger"),
            ("docker", "Docker Compose"),
            ("uv", "uv workspace"),
            ("python", "Python 3.13"),
            ("typescript", "TypeScript"),
        ]
    ):
        b.append(chip_logo(770 + (i % 4) * 157, ay + 44 + (i // 4) * 44, slug, lbl, 147))
    b.append(text(770, ay + 160, "Pyright strict · Ruff · pytest · GitHub Actions", 12.5, MUTE))

    # cross-panel flows
    b.append(
        arrow(
            f"M{sx + sw + 2} {sy + 250} C{sx + sw + 14} {sy + 250}, {px - 14} {py + 91}, {col[0] - 4} {py + 91}"
        )
    )
    b.append(
        arrow(
            f"M{col[2] + cw + 2} {rows[1] + 31} C{rx - 20} {rows[1] + 31}, {rx - 30} {ry + 100}, {rx - 4} {ry + 100}",
            "#F55036",
        )
    )
    b.append(arrow(f"M{px + pw + 2} {ry + 456} H{rx - 4}", "#2496ED"))
    return svg_doc(w, h, "".join(b))


# ---------------------------------------------------------------------------------------- stack


def stack() -> str:
    groups = [
        (
            "Decisions & reasoning",
            [
                ("cloudflare", "Cloudflare Clef"),
                ("lobe-groq", "GroqCloud"),
                ("openrouter", "OpenRouter"),
                ("lobe-openai", "gpt-oss-120b"),
                ("lobe-nvidia", "Nemotron"),
            ],
        ),
        (
            "Agent runtime",
            [
                ("lobe-langgraph", "LangGraph"),
                ("langchain", "LangChain"),
                ("modelcontextprotocol", "MCP"),
                ("pydantic", "Pydantic"),
                ("docker", "Docker sandbox"),
            ],
        ),
        (
            "Observability",
            [
                ("opentelemetry", "OpenTelemetry"),
                ("jaeger", "Jaeger"),
                ("grafana", "Loki"),
                ("prometheus", "Prometheus"),
                ("playwright", "Playwright"),
            ],
        ),
        (
            "Integrations & data",
            [
                ("github", "GitHub"),
                ("jira", "Jira"),
                ("unleash", "Unleash"),
                ("postgresql", "Postgres"),
                ("redis", "Redis"),
            ],
        ),
    ]
    w, rowh = 1280, 104
    h = 28 + rowh * len(groups)
    b = [f'<rect width="{w}" height="{h}" rx="24" fill="{BG}"/>']
    for gi, (title, items) in enumerate(groups):
        y = 14 + gi * rowh
        b.append(text(40, y + 52, title.upper(), 11, MUTE, 700))
        for i, (slug, lbl) in enumerate(items):
            x = 260 + i * 200
            b.append(
                f'<rect x="{x}" y="{y + 12}" width="184" height="80" rx="14" fill="{CARD}" stroke="{LINE}"/>'
            )
            b.append(logo(slug, x + 18, y + 34, 36))
            b.append(text(x + 66, y + 57, lbl, 14, INK, 600))
    return svg_doc(w, h, "".join(b))


# ------------------------------------------------------------------------------------------ gif

SLIDE = """<!doctype html><meta charset=utf-8><style>
body{{margin:0;width:1200px;height:720px;background:#0B0F17;font-family:Inter,-apple-system,Segoe UI,Helvetica,Arial;color:#E6EDF3;overflow:hidden}}
.cap{{position:absolute;left:0;right:0;top:0;height:92px;display:flex;align-items:center;gap:18px;padding:0 36px;
background:linear-gradient(90deg,#1b1640,#0B0F17 70%);border-bottom:1px solid #263042}}
.n{{width:38px;height:38px;border-radius:50%;background:#7C5CFF;display:grid;place-items:center;font-weight:800;font-size:18px;flex:none}}
.t{{font-size:24px;font-weight:700}} .s{{font-size:15px;color:#8B98AD;margin-top:4px}}
.shot{{position:absolute;top:112px;left:0;right:0;bottom:20px;display:grid;place-items:center}}
.shot img{{max-width:1120px;max-height:580px;border-radius:14px;border:1px solid #263042;box-shadow:0 24px 60px #000a}}
.term{{position:absolute;top:112px;left:40px;right:40px;bottom:24px;background:#0d1117;border:1px solid #30363d;border-radius:12px;overflow:hidden}}
.bar{{height:30px;border-bottom:1px solid #30363d;display:flex;gap:8px;align-items:center;padding:0 12px}} .bar i{{width:11px;height:11px;border-radius:50%;display:block}}
pre{{margin:0;padding:14px 18px;font:14.5px/1.5 'JetBrains Mono',SFMono-Regular,Menlo,monospace;white-space:pre-wrap;color:#e6edf3}}
.ok{{color:#3fb950}} .dim{{color:#8b949e}} .hl{{color:#d2a8ff}}
.end{{position:absolute;inset:0;display:grid;place-items:center;text-align:center}}
.end h1{{font-size:64px;margin:0;background:linear-gradient(90deg,#fff,#C9BFFF,#22D3EE);-webkit-background-clip:text;color:transparent}}
.end p{{font-size:22px;color:#C3CCDA}}
</style>{body}"""


def _caption(n: str, title: str, sub: str) -> str:
    return f"<div class=cap><div class=n>{n}</div><div><div class=t>{escape(title)}</div><div class=s>{escape(sub)}</div></div></div>"


def _terminal_lines(run_id: str) -> list[str]:
    sys.path.insert(0, str(ROOT / "scripts"))
    from debugassist.pipeline.cli import _summary  # pyright: ignore[reportPrivateUsage]
    from debugassist.pipeline.state import RunState

    state = RunState.model_validate_json((ROOT / ".data" / "runs" / run_id / "state.json").read_text())
    buf = io.StringIO()
    with redirect_stdout(buf):
        _summary(state)
    head = [
        "$ debugassist run latest --llm mock      # keyless demo: scripted LLM, mock Clef/GitHub/Jira",
        f"run {run_id} (autonomous, LLM mock); artifacts in .data/runs/{run_id}/",
        *[f"  ▶ {n}" for n in state.timings_ms],
        "",
    ]
    return head + [ln[:150] for ln in buf.getvalue().splitlines()]


def _term_html(lines: list[str]) -> str:
    out = []
    for ln in lines:
        e = escape(ln)
        if ln.startswith("$"):
            e = f"<span class=hl>{e}</span>"
        elif "✓" in ln or "passed=True" in ln:
            e = f"<span class=ok>{e}</span>"
        elif ln.startswith("  ▶"):
            e = f"<span class=dim>{e}</span>"
        out.append(e)
    return (
        "<div class=term><div class=bar><i style=background:#ff5f57></i><i style=background:#febc2e></i><i style=background:#28c840></i></div><pre>"
        + "\n".join(out)
        + "</pre></div>"
    )


async def demo_gif(mock_run: str) -> None:
    from playwright.async_api import async_playwright

    story = [
        (
            "01-miniride-home.png",
            "1",
            "A rider taps “your driver is arriving”…",
            "MiniRide 1.6.1 — the demo app DebugAssist debugs",
        ),
        (
            "04-vitals-issue.png",
            "2",
            "…and the app crashes. Vitals groups it.",
            "Symbolicated stack · breadcrumbs · every crashing session has notif_router_v2 on",
        ),
        (
            "06-bugdrop-report.png",
            "3",
            "Riders report it in-app too",
            "BugDrop: description, screenshot, UI-state timeline, logs",
        ),
        (
            "07-unleash-flag.png",
            "4",
            "The flag behind it: a 5% rollout",
            "Unleash gradual rollout of the new notification router",
        ),
        (
            "02-jaeger-trace.png",
            "5",
            "Every request is traced",
            "OpenTelemetry → Jaeger across client, gateway and dispatch",
        ),
    ]
    lines = _terminal_lines(mock_run)
    report = ROOT / ".data" / "runs" / mock_run / "report.html"
    from debugassist.pipeline.report import render

    report.write_text(render(mock_run))
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        frames: list[tuple[Path, float]] = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            page = await browser.new_page(viewport={"width": 1200, "height": 720})

            async def slide(body: str, seconds: float) -> None:
                f = t / f"f{len(frames):03d}.png"
                (t / "s.html").write_text(SLIDE.format(body=body))
                await page.goto((t / "s.html").as_uri())
                await page.wait_for_timeout(120)
                await page.screenshot(path=str(f))
                frames.append((f, seconds))

            for shot, n, title, sub in story:
                await slide(
                    _caption(n, title, sub) + f'<div class=shot><img src="{(SHOTS / shot).as_uri()}"></div>',
                    2.6,
                )
            cap = _caption(
                "6",
                "DebugAssist takes it from here",
                "One command: triage → root cause → mitigation → reproduce + fix → validate → PR (keyless demo shown)",
            )
            cmd = lines[0]
            for k in range(8, len(cmd) + 8, 8):
                await slide(cap + _term_html([cmd[:k] + "▌"]), 0.06)
            for k in range(2, len(lines) + 1):
                await slide(cap + _term_html(lines[:k]), 0.35 if lines[k - 1].startswith("  ▶") else 0.12)
            frames[-1] = (frames[-1][0], 3.2)
            await page.goto(report.as_uri())
            await page.wait_for_timeout(300)
            rp = t / "report.png"
            await page.screenshot(path=str(rp), full_page=False)
            await slide(
                _caption(
                    "7",
                    "Every run is documented",
                    "debugassist report: decisions · evidence · diff · validation proof · audited writes (shown: the keyless demo run)",
                )
                + f'<div class=shot><img src="{rp.as_uri()}"></div>',
                3.0,
            )
            await slide(
                '<div class=end><div><h1>DebugAssist</h1><p>crash → root cause → validated pull request</p><p style="font-size:16px;color:#8B98AD">github.com/IshaanNene/DebugAssist</p></div></div>',
                2.6,
            )
            await browser.close()
        concat = t / "list.txt"
        concat.write_text(
            "".join(f"file '{f}'\nduration {d}\n" for f, d in frames) + f"file '{frames[-1][0]}'\n"
        )
        out = ASSETS / "demo.gif"
        vf = "fps=12,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=192:stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a"
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        args = [
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat),
            "-vf",
            vf,
            "-loop",
            "0",
            str(out),
        ]
        proc = await asyncio.create_subprocess_exec(ffmpeg, *args)
        if await proc.wait():
            raise SystemExit("ffmpeg failed")
        print(f"{out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")


def main(argv: list[str]) -> None:
    what = argv[0] if argv else "all"
    ASSETS.mkdir(parents=True, exist_ok=True)
    if what in ("svg", "all"):
        for name, fn in (("hero", hero), ("architecture", architecture), ("stack", stack)):
            (ASSETS / f"{name}.svg").write_text(fn())
            print(f"docs/assets/{name}.svg")
    if what in ("gif", "all"):
        if not shutil.which("ffmpeg"):
            raise SystemExit("ffmpeg is required for demo.gif")
        runs = sorted((ROOT / ".data" / "runs").glob("*/state.json"), key=lambda p: p.stat().st_mtime)
        mock = next((p.parent.name for p in reversed(runs) if '"llm_mode": "mock"' in p.read_text()), None)
        if mock is None:
            raise SystemExit("no mock run found: run `make demo-push-crash` first")
        asyncio.run(demo_gif(mock))


if __name__ == "__main__":
    main(sys.argv[1:])
