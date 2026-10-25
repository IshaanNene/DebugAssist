# Site redesign plan (apps/site)

Status: P0–P2 built 2026-10-25 (see [PROGRESS.md](PROGRESS.md#site-redesign-foundations-and-the-home-page-2026-10-25)); P3–P4 open. The original visual plan, with a hero sketch: https://claude.ai/artifact/PzokmUJ4wCPYEgivaCsKD2 (private until shared).

## What was built, and what changed from the plan

- **Home** (`app/page.tsx`): hero with the run console (`RunConsole.tsx`), then the three actors, the pipeline, the
  layers, features, a results summary and a Safety section (`Sections.tsx`), integrations, start, FAQ.
  ~11,300 px at 1440 px wide; the ≤ 7,000 px target is not met yet — features and the lower sections are the next cut.
- **`/results`** (`app/results/page.tsx`): the evaluation tables, moved unchanged. `/how-it-works`, `/runs` and
  `/start` are not built; how-it-works content lives on the home page for now.
- **Receipt uses the Popover API, not Base UI.** Base UI's popover cost 45 KB gzipped on first load; the platform
  gives light dismiss, Escape, the top layer and an accessible invoker, and CSS anchor positioning places it (with a
  measured fallback). Base UI stays the choice for the ⌘K dialog in P4, loaded on demand.
- **The JS budget was wrong.** React and Next.js alone ship ~126 KB gzipped, so "≤ 120 KB on `/`" cannot hold. The
  budget is now the site's own share: ≤ 55 KB gzipped on top of the framework (today: 177.4 KB total, ~51 KB ours).
- **Timecode rail** became the console's own clock and phase bands; a page-wide rail was not built.
- **Run timings** are exported by `debugassist eval timings` (and by `eval report`) into `run-timings.json`.

## Why

The current site reads as copied: its visual vocabulary is the shared 2024–25 dev-tool template.

| Pattern | Where | Verdict |
|-|-|-|
| Warm paper background, corner-bracket cells | `.cbox`, `--surface-bg` | drop |
| Hatching and drafting grid as texture | `.stripes`, `.drafting` | drop (hatch only marks a miss) |
| Yellow highlighter on headline phrases | `<Mark>`, `.mark-ink` | drop |
| Hatched isometric slabs | `.hero-bg`, `Loop.tsx` | drop |
| Geist + Geist Mono + Inter | `app/layout.tsx` | replace |
| Marquee, spotlight cards, word-by-word reveal, floating card, outlined wordmark | `.marquee`, `.spot`, `.word`, `.float-card`, `.wordmark` | drop |
| One ~16,800 px page for every audience | `app/page.tsx` | split |

Keep: misses in neutral hatch (never red); every figure computed from `evals/reports` by `src/lib/data.ts`; the real-run replay; G/D/R/S shortcuts; SSR-complete content with motion armed by `html.js`; the "what doesn't work yet" column.

## Decisions

- **D1** Retire the borrowed vocabulary above.
- **D2 Scroll is time.** Home replays one evaluated run (VIT-1001, run `20261007-042922-vit-1001`) from crash to hidden test; a timecode sits in the header.
- **D3 Every number is a receipt.** Figures render only through `<Receipt source=…>`; tapping shows file, row, field, raw value.
- **D4 Three voices.** Claims: Archivo (wdth 62–125). Evidence: Martian Mono (wdth 75–112.5). Caveats: Newsreader Italic. All OFL, self-hosted via `next/font/google`.
- **D5** One animation runtime (Motion), one WebGL moment (OGL, P4, optional), native scrolling.

## Tokens

Night shift and day shift from one definition: each token is `light-dark(day, night)` in `app/globals.css`. The site follows the system setting; the header toggle pins one.

| Token | Night | Day | Role |
|-|-|-|-|
| `--bg` | #0E1421 | #F4F6FA | page |
| `--raised` | #151C2B | #FFFFFF | panels |
| `--fg` / `--fg-2` / `--fg-3` / `--fg-4` | #E9EDF4 / #AFB8C9 / #8F9AB0 / #7C879D | #111A2C / #3B465C / #596479 / #646E82 | text |
| `--amber` | #FFB547 | #9A5B00 | time and action only (timecode, primary button, focus) |
| `--actor-clef` | #3FD0C0 | #0B7C73 | Clef decisions |
| `--actor-llm` | #AA9CFF | #5A48D0 | LLM agents |
| `--actor-code` | #C9D1DE | #3B465C | deterministic code |
| `--pass` | #6BDB98 | #18794A | checks passed |
| `--signal` | #FF7A85 | #C42F44 | the incoming crash; the only red |

Every text token is ≥ 4.5:1 on its theme's `--bg` (WCAG 2 formula). Ink on the amber button: 9.9:1.

Motion: `--t-press` 90 ms; `--t-ui` 180 ms `cubic-bezier(.2,.8,.2,1)`; `--t-reveal` 420 ms `cubic-bezier(.16,1,.3,1)`, 8 px rise from a visible state; replay is a linear clock at 10/30/60×. CSS scroll timelines where supported (Chrome/Edge 115+, Safari 26+), Motion fallback for Firefox. Reduced motion: the replay steps between finished steps.

## Components

Timecode rail · Receipt · Run waterfall (true time axis, actor colors, a diamond per Clef decision) · Run receipt (also the OG image) · Verdict cells (shape + color) · Bisect strip (from `bisect-replay.json`) · Policy manifest (renders `configs/policies/writes.yaml` at build) · ⌘K palette.

## Pages

| Route | Job | Data |
|-|-|-|
| `/` | replay one run, headline results, start (≤ ~7,000 px) | `featuredRun()`, `results()` |
| `/results` | lab notebook: every measurement with its report and caveats | `results()`, `realBugs()`, `deciderReplay()`, `fixWidth()`, `bisectReplay()`, `contextArms()` |
| `/how-it-works` | four layers, fixed plan, MCP evidence, policy gate | `facts()`, `writes.yaml` |
| `/runs`, `/runs/[id]` | replay any evaluated run | per-run JSON exported into `evals/reports` (new) |
| `/start` | keyless demo, GitHub App, self-hosting | README, `docs/github-app.md` |

Per-step timings come from `run-timings.json` (exported from `.data/runs/<id>/nodes/*.json`). The featured run stopped after `validate` and opened no PR; the Ship section must use a separate run that shipped, labelled as such.

## Stack (npm, 2026-10-25)

In use: Next.js 16.4.2 · React 19.2.8 · Tailwind 4 · the Popover API. Planned: Next.js 16.4.3 · React 19.3.1 · Motion 14.6.0 · Base UI (`@base-ui/react`) 1.9.0, for ⌘K only · cmdk 1.1.1 · Shiki 4.5.0 · `@number-flow/react` 0.6.2 · OGL 1.0.11 · Playwright 1.64.1, `@axe-core/playwright` 4.14.0, `@lhci/cli` 0.15.1.

Not chosen: shadcn/Magic UI/Aceternity styling (the template look), GSAP 3.15 (second runtime), Lenis (scroll hijack), R3F/three (3D isn't the story), Paper Shaders (pre-1.0), Spline/Lottie (heavy). React `ViewTransition` is still experimental in Next 16: `/runs` only, never required.

## Done means

- Lighthouse mobile LCP ≤ 1.8 s, CLS ≤ 0.02, INP ≤ 150 ms; the site's own first-load JS on `/` ≤ 55 KB gz on top of React and Next.js; fonts ≤ 150 KB.
- WCAG 2.2 AA in both themes, axe clean in CI, replay has a stop control, no state by color alone.
- A lint rule fails the build on a bare digit in JSX text outside an allowlist; a Playwright test checks every receipt points at a file in `evals/reports`.
- Visual regression at 375/768/1280 px in both themes.

## Build order (one PR each)

- **P0 Foundations** ✅ tokens, fonts, Receipt, remove borrowed CSS, export run timings.
- **P1 Home** ✅ hero replay, actors, pipeline, layers, results summary, safety. Still to do: the Ship section from a
  run that shipped, a shorter page.
- **P2 `/results`** ✅ tables moved, verdict cells. Still to do: the bisect strip.
- **P3 `/runs`:** index + replay pages, run-receipt OG images.
- **P4 Polish:** ⌘K, WebGL field, `/how-it-works`, Lighthouse CI, visual regression.

## Open calls

Decided: headline "On call, with receipts.", follow the system theme, the free font trio. Open: WebGL field (P4, cut if over budget); Martian Grotesk later.
