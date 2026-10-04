"""Build the README visuals into docs/assets/ (make readme-assets).

    uv run --no-sync python scripts/readme_assets.py [svg|gif|all]

* hero.svg, overview.svg, pipeline.svg, miniride.svg, stack.svg — hand-laid SVG with brand logos embedded as vector paths
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


# ------------------------------------------------------------------------------- diagrams
# Three diagrams in one visual language: few words, one accent per role, generous spacing,
# smooth connectors. Roles: Clef = orange, LLM agents = violet, deterministic proof = green.

CLEF, LLM, PROOF, CODE = "#F38020", "#A78BFA", "#34D399", "#64748B"
EDGE = "#3A4560"


def defs(*extra: str) -> str:
    return (
        "<defs>"
        f'<marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 1.5L8.5 5L0 8.5z" fill="{EDGE}"/></marker>'
        '<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="#FFFFFF" fill-opacity=".045"/></pattern>'
        f'<linearGradient id="cardg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#161D2C"/><stop offset="1" stop-color="#11172A"/></linearGradient>'
        + "".join(extra)
        + "</defs>"
    )


def canvas(w: int, h: int) -> str:
    return f'<rect width="{w}" height="{h}" rx="24" fill="{BG}"/><rect width="{w}" height="{h}" rx="24" fill="url(#dots)"/>'


def box(x: float, y: float, w: float, h: float, accent: str | None = None, r: int = 18) -> str:
    stroke = f'stroke="{accent}" stroke-opacity=".55"' if accent else f'stroke="{LINE}"'
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="url(#cardg)" {stroke}/>'


def icon_tile(x: float, y: float, inner: str, tint: str, size: int = 44) -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="12" fill="{tint}" fill-opacity=".14"/>'
        + inner
    )


def dot_icon(cx: float, cy: float, color: str) -> str:
    return f'<circle cx="{cx}" cy="{cy}" r="8" fill="{color}"/><circle cx="{cx}" cy="{cy}" r="13" fill="none" stroke="{color}" stroke-opacity=".35" stroke-width="2"/>'


def entity(
    x: float, y: float, w: float, title: str, sub: str, icon: str, tint: str, accent: str | None = None
) -> str:
    """A card with an icon tile, a title and one short line."""
    h = 76
    return (
        box(x, y, w, h, accent)
        + icon_tile(x + 16, y + 16, icon, tint)
        + text(x + 76, y + 34, title, 16, INK, 700)
        + text(x + 76, y + 56, sub, 12.5, MUTE, 500)
    )


def curve(
    x1: float, y1: float, x2: float, y2: float, color: str = EDGE, flow: bool = False, width: float = 1.6
) -> str:
    mx = (x1 + x2) / 2
    cls = ' class="flow"' if flow else ""
    return f'<path d="M{x1} {y1} C{mx} {y1}, {mx} {y2}, {x2 - 2} {y2}" fill="none" stroke="{color}" stroke-width="{width}" marker-end="url(#ah)"{cls}/>'


def vline(x: float, y1: float, y2: float, color: str = EDGE) -> str:
    return f'<path d="M{x} {y1} V{y2 - 2}" fill="none" stroke="{color}" stroke-width="1.6" marker-end="url(#ah)"/>'


def label(x: float, y: float, s: str, color: str = MUTE) -> str:
    return text(x, y, s.upper(), 11, color, 700)


def tag(x: float, y: float, s: str, color: str) -> str:
    w = 16 + len(s) * 6.4
    return (
        f'<rect x="{x - w / 2}" y="{y - 12}" width="{w}" height="22" rx="11" fill="{BG}" stroke="{color}" stroke-opacity=".6"/>'
        + text(x, y + 3.5, s, 11, color, 700, "middle")
    )


def overview() -> str:
    w, h = 1400, 760
    b = [defs(), canvas(w, h)]
    b.append(text(56, 64, "DebugAssist at a glance", 24, INK, 800))
    b.append(text(56, 92, "Signals in, a validated pull request out.", 15, MUTE, 500))

    # signals
    sx, sw, ys = 56, 280, [250, 350, 450]
    b.append(label(sx, 228, "Signals"))
    b.append(
        entity(
            sx,
            ys[0],
            sw,
            "Vitals",
            "crashes, hangs, jank",
            dot_icon(sx + 38, ys[0] + 38, "#F43F5E"),
            "#F43F5E",
        )
    )
    b.append(
        entity(
            sx,
            ys[1],
            sw,
            "BugDrop",
            "in-app bug reports",
            dot_icon(sx + 38, ys[1] + 38, "#F59E0B"),
            "#F59E0B",
        )
    )
    b.append(
        entity(
            sx,
            ys[2],
            sw,
            "Telemetry",
            "traces · logs · metrics",
            logo("opentelemetry", sx + 26, ys[2] + 26, 24),
            "#F5A800",
        )
    )
    b.append(text(sx, 566, "from MiniRide, driven by simulated riders", 12, "#5B6782", 500))

    # core
    cx, cw, cy, ch = 520, 360, 300, 176
    b.append(box(cx, cy, cw, ch, ACCENT, 22))
    b.append(
        f'<circle cx="{cx + 34}" cy="{cy + 39}" r="7" fill="{ACCENT}"/><circle cx="{cx + 34}" cy="{cy + 39}" r="12" fill="none" stroke="{ACCENT}" stroke-opacity=".4" stroke-width="2"/>'
    )
    b.append(text(cx + 56, cy + 46, "DebugAssist", 22, INK, 800))
    b.append(text(cx + 24, cy + 82, "A fixed LangGraph plan — models never", 13, MUTE, 500))
    b.append(text(cx + 24, cy + 101, "choose the next step.", 13, MUTE, 500))
    steps = ["Triage", "Root cause", "Fix", "Validate"]
    for i, st in enumerate(steps):
        tx = cx + 24 + i * 82
        b.append(
            f'<rect x="{tx}" y="{cy + 124}" width="74" height="28" rx="14" fill="{ACCENT}" fill-opacity=".14"/>'
        )
        b.append(text(tx + 37, cy + 142, st, 11.5, "#C4B5FD", 700, "middle"))

    # clef (above)
    kx, ky, kw = cx + 30, 140, cw - 60
    b.append(box(kx, ky, kw, 80, CLEF))
    b.append(icon_tile(kx + 16, ky + 18, logo("cloudflare", kx + 22, ky + 26, 32), CLEF))
    b.append(text(kx + 76, ky + 36, "Clef decides", 16, INK, 700))
    b.append(text(kx + 76, ky + 58, "calibrated calls at 18 decision points", 12.5, MUTE, 500))
    b.append(vline(cx + cw / 2, ky + 80, cy, CLEF))

    # llm + tools (below)
    ly = 560
    lw = (cw - 16) / 2
    b.append(box(cx, ly, lw, 96, LLM))
    b.append(logo("lobe-groq", cx + 18, ly + 18, 22) + logo("openrouter", cx + 48, ly + 18, 22))
    b.append(text(cx + 18, ly + 66, "LLMs reason", 15, INK, 700))
    b.append(text(cx + 18, ly + 84, "GroqCloud · OpenRouter", 11.5, MUTE, 500))
    tx2 = cx + lw + 16
    b.append(box(tx2, ly, lw, 96, "#2496ED"))
    b.append(logo("modelcontextprotocol", tx2 + 18, ly + 18, 22) + logo("docker", tx2 + 50, ly + 18, 24))
    b.append(text(tx2 + 18, ly + 66, "Tools & sandbox", 15, INK, 700))
    b.append(text(tx2 + 18, ly + 84, "MCP · network-less Docker", 11.5, MUTE, 500))
    b.append(vline(cx + lw / 2, cy + ch, ly, LLM))
    b.append(vline(tx2 + lw / 2, cy + ch, ly, "#2496ED"))

    # outcomes
    ox, ow = 1064, 280
    b.append(label(ox, 228, "Outcomes"))
    b.append(
        entity(
            ox,
            ys[0],
            ow,
            "Pull request",
            "fix + regression test",
            logo("github", ox + 26, ys[0] + 26, 24),
            "#E6EDF3",
            PROOF,
        )
    )
    b.append(
        entity(
            ox,
            ys[1],
            ow,
            "Jira ticket",
            "root cause + evidence",
            logo("jira", ox + 26, ys[1] + 26, 24),
            "#4C9AFF",
        )
    )
    b.append(
        entity(
            ox,
            ys[2],
            ow,
            "Flag rollback",
            "proposed, needs approval",
            logo("unleash", ox + 24, ys[2] + 24, 28),
            "#9CA3AF",
        )
    )
    b.append(text(ox, 566, "every write: policy-gated and audited", 12, "#5B6782", 500))

    # connectors
    for y in ys:
        b.append(curve(sx + sw, y + 38, cx, cy + ch / 2, EDGE, flow=True))
    for y in ys:
        b.append(curve(cx + cw, cy + ch / 2, ox, y + 38, EDGE, flow=True))
    b.append(tag(cx + cw + 92, cy + ch / 2 - 1, "policy gate", PROOF))

    # footer
    b.append(f'<line x1="56" y1="{h - 64}" x2="{w - 56}" y2="{h - 64}" stroke="{LINE}"/>')
    foot = ["Sandboxed agents", "Proof before PR", "Bot branches only", "Audit log", "Mock mode for CI"]
    for i, f in enumerate(foot):
        b.append(text(56 + i * 262, h - 32, "✓ " + f, 13, "#94A3B8", 600))
    return svg_doc(w, h, "".join(b))


def pipeline() -> str:
    w, h = 1400, 470
    b = [defs(), canvas(w, h)]
    b.append(text(56, 64, "The pipeline", 24, INK, 800))
    b.append(text(56, 92, "Ten steps, always in this order. Checkpointed after each one.", 15, MUTE, 500))
    steps = [
        ("Ingest", "read the issue", CODE, None),
        ("Triage", "owner · priority", CODE, "D01"),
        ("Context", "collect evidence", CODE, None),
        ("Root cause", "agent + evidence", LLM, "D05"),
        ("Mitigate", "flag z-test", CODE, "D11"),
        ("Reproduce", "failing test", LLM, None),
        ("Fix", "smallest change", LLM, None),
        ("Validate", "fail → pass", PROOF, "D15"),
        ("Ship gate", "PR or draft", CODE, "D16"),
        ("PR + ticket", "push · link", PROOF, None),
    ]
    x0, gap, y = 104, 132, 250
    xs = [x0 + i * gap for i in range(len(steps))]
    b.append(
        f'<line x1="{xs[0]}" y1="{y}" x2="{xs[-1]}" y2="{y}" stroke="{LINE}" stroke-width="3" stroke-linecap="round"/>'
    )
    b.append(
        f'<line x1="{xs[0]}" y1="{y}" x2="{xs[-1]}" y2="{y}" stroke="{ACCENT}" stroke-opacity=".45" stroke-width="3" class="flow"/>'
    )
    for i, (x, (name, sub, color, dec)) in enumerate(zip(xs, steps, strict=True)):
        if dec:
            b.append(
                f'<line x1="{x}" y1="{y - 60}" x2="{x}" y2="{y - 28}" stroke="{CLEF}" stroke-opacity=".6" stroke-width="1.5" stroke-dasharray="3 4"/>'
            )
            b.append(
                f'<g transform="translate({x} {y - 76}) rotate(45)"><rect x="-13" y="-13" width="26" height="26" rx="5" fill="#2A1A08" stroke="{CLEF}"/></g>'
            )
            b.append(text(x, y - 72, dec[1:], 10.5, "#FDBA74", 800, "middle"))
        b.append(f'<circle cx="{x}" cy="{y}" r="26" fill="{BG}" stroke="{color}" stroke-width="2.5"/>')
        b.append(f'<circle cx="{x}" cy="{y}" r="19" fill="{color}" fill-opacity=".16"/>')
        b.append(text(x, y + 5, str(i + 1), 14, INK, 800, "middle"))
        b.append(text(x, y + 56, name, 14.5, INK, 700, "middle"))
        b.append(text(x, y + 76, sub, 11.5, MUTE, 500, "middle"))
    # retry loop validate -> reproduce
    a, c = xs[7], xs[5]
    b.append(
        f'<path d="M{a} {y + 92} C{a} {y + 128}, {c} {y + 128}, {c} {y + 92}" fill="none" stroke="{PROOF}" stroke-opacity=".7" stroke-width="1.6" stroke-dasharray="5 5" marker-end="url(#ah)"/>'
    )
    b.append(text((a + c) / 2, y + 136, "retry up to 3×", 11.5, PROOF, 700, "middle"))
    b.append(
        f'<circle r="5" fill="#FFFFFF"><animateMotion dur="7s" repeatCount="indefinite" path="M{xs[0]},{y} L{xs[-1]},{y}"/></circle>'
    )
    # legend
    ly = h - 46
    items = [
        (LLM, "LLM agent"),
        (CLEF, "Clef decision (D01–D18)"),
        (PROOF, "deterministic proof / write"),
        (CODE, "deterministic code"),
    ]
    for i, (color, s) in enumerate(items):
        lx = 56 + i * 300
        b.append(f'<circle cx="{lx + 7}" cy="{ly - 4}" r="6" fill="{color}"/>')
        b.append(text(lx + 22, ly + 1, s, 13, "#94A3B8", 600))
    return svg_doc(w, h, "".join(b))


def miniride() -> str:
    w, h = 1400, 640
    b = [defs(), canvas(w, h)]
    b.append(text(56, 64, "MiniRide — the system under test", 24, INK, 800))
    b.append(text(56, 92, "A small ride-hailing app with real services, flags and telemetry.", 15, MUTE, 500))
    b.append('<g transform="translate(0 40)">')
    # client
    b.append(entity(56, 240, 270, "Rider app", "React PWA · :8080", logo("react", 82, 266, 24), "#61DAFB"))
    # gateway
    b.append(
        entity(430, 240, 270, "Gateway", "GraphQL · Node · :4000", logo("graphql", 456, 266, 24), "#E10098")
    )
    # services
    b.append(
        entity(
            804, 160, 270, "Dispatch", "FastAPI · Python · :8001", logo("fastapi", 830, 186, 24), "#009688"
        )
    )
    b.append(entity(804, 320, 270, "Payments", "Go · :8002", logo("go", 828, 188 + 160, 28), "#00ADD8"))
    b.append(
        entity(1100, 160, 244, "Postgres", "rides, places", logo("postgresql", 1126, 186, 24), "#4169E1")
    )
    # flags
    b.append(entity(430, 100, 270, "Unleash", "feature flags", logo("unleash", 454, 124, 28), "#9CA3AF"))
    # edges
    b.append(curve(326, 278, 430, 278, EDGE, flow=True))
    b.append(tag(378, 262, "GraphQL", "#94A3B8"))
    b.append(curve(700, 278, 804, 198, EDGE, flow=True))
    b.append(curve(700, 278, 804, 358, EDGE, flow=True))
    b.append(curve(1074, 198, 1100, 198, EDGE))
    b.append(
        f'<path d="M191 240 C191 160, 300 138, 428 138" fill="none" stroke="{EDGE}" stroke-width="1.6" stroke-dasharray="4 5" marker-end="url(#ah)"/>'
    )
    b.append(text(206, 172, "flags", 11.5, MUTE, 600))
    # telemetry bar
    ty = 450
    b.append(box(56, ty, 1288, 96, "#F5A800"))
    b.append(icon_tile(76, ty + 26, logo("opentelemetry", 84, ty + 34, 28), "#F5A800"))
    b.append(text(136, ty + 44, "OpenTelemetry everywhere", 16, INK, 700))
    b.append(
        text(
            136,
            ty + 66,
            "W3C trace context flows browser → gateway → services; every service ships traces, logs and metrics.",
            12.5,
            MUTE,
            500,
        )
    )
    for i, (slug, s) in enumerate([("jaeger", "Jaeger"), ("grafana", "Loki"), ("prometheus", "Prometheus")]):
        x = 980 + i * 120
        b.append(logo(slug, x, ty + 34, 24) + text(x + 32, ty + 52, s, 13, INK, 600))
    for x in (191, 565, 939):
        b.append(
            f'<line x1="{x}" y1="{ty - 2}" x2="{x}" y2="{316 if x != 939 else 396}" stroke="#F5A800" stroke-opacity=".35" stroke-width="1.5" stroke-dasharray="3 5"/>'
        )
    b.append("</g>")
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
        for name, fn in (
            ("hero", hero),
            ("overview", overview),
            ("pipeline", pipeline),
            ("miniride", miniride),
            ("stack", stack),
        ):
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
