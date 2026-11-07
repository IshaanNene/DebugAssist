"use client";

import { useEffect, useRef, useState } from "react";

type Kind = "code" | "llm" | "clef";

interface Step {
  name: string;
  kind: Kind[]; // what does the work: the first is the main actor
  d?: string; // the Clef decisions taken in this step
}

interface Phase {
  name: string;
  steps: string;
  decisions: string;
  kind: Kind[];
  what: string;
  parts: Step[];
}

// The fixed plan (ADR 0001) in four phases; the sub-phases are the pipeline's actual steps, always in this order.
// Each step's kinds and decisions follow the decision templates' `stage` (packages/decisions/templates).
const PHASES: Phase[] = [
  {
    name: "Detect",
    steps: "ingest · triage · dedup",
    decisions: "D01 · D02",
    kind: ["code", "clef"],
    what: "A crash from Vitals or a rider's report from BugDrop comes in. Owner from CODEOWNERS, priority and severity, dedup against open issues, a ticket and a page.",
    parts: [
      { name: "Ingest", kind: ["code"] },
      { name: "Triage", kind: ["clef"], d: "D01" },
      { name: "Dedup", kind: ["clef"], d: "D02" },
    ],
  },
  {
    name: "Investigate",
    steps: "context · root cause · mitigate",
    decisions: "D03 – D11",
    kind: ["code", "llm", "clef"],
    what: "A deterministic evidence bundle from eleven MCP servers; an agent and its subagents explain the defect, every claim checked against its evidence; a flag rollback is proposed when the numbers say so.",
    parts: [
      { name: "Context", kind: ["code", "clef"], d: "D03 D04" },
      { name: "Root cause", kind: ["llm", "clef"], d: "D05–D10" },
      { name: "Mitigate", kind: ["clef"], d: "D11" },
    ],
  },
  {
    name: "Fix",
    steps: "reproduce · fix · validate",
    decisions: "D12 – D15",
    kind: ["llm", "clef"],
    what: "A test that fails on the shipped release, the smallest fix that makes it pass, then proof: fails before, passes after, suite and CI green — or another attempt.",
    parts: [
      { name: "Reproduce", kind: ["llm"] },
      { name: "Fix", kind: ["llm", "clef"], d: "D12 D13" },
      { name: "Validate", kind: ["code", "clef"], d: "D14 D15" },
    ],
  },
  {
    name: "Ship",
    steps: "ship gate · pull request · watch",
    decisions: "D16 · D17",
    kind: ["code", "clef"],
    what: "A pull request or a draft, decided by the evidence, linked from the ticket. After the deploy, watch the crash rate and resolve or reopen.",
    parts: [
      { name: "Ship gate", kind: ["clef"], d: "D16" },
      { name: "Pull request", kind: ["code"] },
      { name: "Watch", kind: ["code", "clef"], d: "D17" },
    ],
  },
];

const KIND: Record<Kind, { label: string; color: string }> = {
  code: { label: "deterministic code", color: "#cfcfc9" },
  llm: { label: "LLM agents", color: "#8b7cf0" },
  clef: { label: "Clef decisions", color: "#e0901b" },
};

// Isometric projection: x runs down-right (towards the viewer), y runs up-right, z is height.
const C = Math.cos(Math.PI / 6);
const S = Math.sin(Math.PI / 6);
const iso = (x: number, y: number, z = 0): [number, number] => [(x + y) * C, (x - y) * S - z];
const P = (...p: [number, number][]) => p.map(([a, b]) => `${a.toFixed(1)},${b.toFixed(1)}`).join(" ");
/** Text lying on a horizontal face at height z, reading along +y. */
const flat = (x: number, y: number, z: number) => {
  const [tx, ty] = iso(x, y, z);
  return `matrix(${C} ${-S} ${C} ${S} ${tx.toFixed(1)} ${ty.toFixed(1)})`;
};
/** Text lying on a horizontal face at height z, reading along +x (towards the viewer). */
const flatX = (x: number, y: number, z: number) => {
  const [tx, ty] = iso(x, y, z);
  return `matrix(${C} ${S} ${-C} ${S} ${tx.toFixed(1)} ${ty.toFixed(1)})`;
};

const INK = "#2f2e2a";
const FONT = "var(--font-geist-mono), ui-monospace, monospace";

// four phase blocks on one track; the current phase opens into its three steps
const W = 128; // along x
const SD = 44; // one step's slice along y
const SG = 7; // gap between slices
const D = 3 * SD + 2 * SG; // a phase along y
const GAP = 30;
const STEP = D + GAP;
const H_ON = 58;
const H_OFF = 38;
const LANE = 40; // track strip in front of the blocks
const TH = 10;

type Tone = "on" | "done" | "next";
const TONE: Record<Tone, { ink: string; top: string; side: string; front: string; text: string }> = {
  on: { ink: INK, top: "#ffffff", side: "#e9e9e3", front: "#dcdcd6", text: INK },
  done: { ink: "#6f6d66", top: "#fcfcf9", side: "#ecece6", front: "#e2e2dc", text: "#55544e" },
  next: { ink: "#a9a79e", top: "#fbfbf9", side: "#f0f0ec", front: "#e8e8e3", text: "#97958c" },
};

function Block({ x, y, w, d, h, tone }: { x: number; y: number; w: number; d: number; h: number; tone: Tone }) {
  const t = TONE[tone];
  const top = [iso(x, y, h), iso(x, y + d, h), iso(x + w, y + d, h), iso(x + w, y, h)];
  const front = [iso(x + w, y, h), iso(x + w, y + d, h), iso(x + w, y + d, 0), iso(x + w, y, 0)];
  const side = [iso(x, y, h), iso(x + w, y, h), iso(x + w, y, 0), iso(x, y, 0)];
  return (
    <g strokeLinejoin="round" stroke={t.ink}>
      <polygon points={P(...side)} fill={t.side} strokeWidth={1} />
      <polygon points={P(...front)} fill={t.front} strokeWidth={1} />
      <polygon points={P(...top)} fill={t.top} strokeWidth={1.15} />
    </g>
  );
}

/** A small square lying on a top face: the colour of what does the work. */
function Tile({ x, y, z, kind, faded }: { x: number; y: number; z: number; kind: Kind; faded?: boolean }) {
  const s = 10;
  return (
    <polygon
      points={P(iso(x, y, z), iso(x, y + s, z), iso(x + s, y + s, z), iso(x + s, y, z))}
      fill={KIND[kind].color}
      fillOpacity={faded ? 0.7 : 1}
      stroke={INK}
      strokeOpacity={faded ? 0.5 : 0.85}
      strokeWidth={0.9}
    />
  );
}

function Diagram({ active, onSelect }: { active: number; onSelect: (i: number) => void }) {
  const n = PHASES.length;
  const len = n * STEP - GAP;
  const t0x = -20;
  const t1x = W + LANE;
  const t0y = -40;
  const t1y = len + 40;
  const trackTop = [iso(t0x, t0y), iso(t0x, t1y), iso(t1x, t1y), iso(t1x, t0y)];
  const trackFront = [iso(t1x, t0y), iso(t1x, t1y), iso(t1x, t1y, -TH), iso(t1x, t0y, -TH)];
  const trackEnd = [iso(t0x, t0y), iso(t1x, t0y), iso(t1x, t0y, -TH), iso(t0x, t0y, -TH)];

  // a fixed frame for every phase, so the view never jumps
  const ext = [...trackTop, iso(t1x, t0y, -TH), iso(t1x, t1y, -TH), iso(0, 0, H_ON + 14), iso(0, len, H_ON + 14), iso(t1x + 40, t0y - 80), iso(t1x + 40, t1y + 86)];
  const pad = 22;
  const minX = Math.min(...ext.map((p) => p[0])) - pad;
  const maxX = Math.max(...ext.map((p) => p[0])) + pad;
  const minY = Math.min(...ext.map((p) => p[1])) - pad;
  const maxY = Math.max(...ext.map((p) => p[1])) + pad;

  const order = PHASES.map((_, i) => i).sort((a, b) => b - a); // larger y is further back
  const tone = (i: number): Tone => (i === active ? "on" : i < active ? "done" : "next");

  return (
    <svg
      viewBox={`${minX.toFixed(0)} ${minY.toFixed(0)} ${(maxX - minX).toFixed(0)} ${(maxY - minY).toFixed(0)}`}
      className="block h-auto max-h-[64vh] w-full select-none"
      role="img"
      aria-label={`The DebugAssist pipeline in four phases: ${PHASES.map((p) => p.name).join(", ")}. Showing ${PHASES[active].name}: ${PHASES[active].parts.map((s) => s.name).join(", ")}.`}
    >
      {/* track */}
      <polygon points={P(...trackEnd)} fill="#dde05f" stroke={INK} strokeWidth={1} />
      <polygon points={P(...trackFront)} fill="#e9ec6c" stroke={INK} strokeWidth={1} />
      <polygon points={P(...trackTop)} fill="#f7f985" stroke={INK} strokeWidth={1.1} />
      <polyline
        className="flow"
        points={P(iso(W + 10, t0y + 10), iso(W + 10, t1y - 10))}
        fill="none"
        stroke={INK}
        strokeOpacity={0.35}
        strokeWidth={1}
        strokeDasharray="4 10"
      />
      <text transform={flat(t1x + 24, t0y - 74, 0)} fontFamily={FONT} fontSize={12} fill="#55544e">
        signal in →
      </text>
      <text transform={flat(t1x + 24, t1y - 2, 0)} fontFamily={FONT} fontSize={12} fill="#55544e">
        → proof out
      </text>

      {order.map((i) => {
        const ph = PHASES[i];
        const on = i === active;
        const t = tone(i);
        const y0 = i * STEP;
        return (
          <g key={ph.name} onClick={() => onSelect(i)} className="cursor-pointer">
            {/* the open phase's top holds its steps, so its name goes on the lane in front */}
            {on && (
              <text transform={flat(W + 26, y0 + 4, 0)} fontFamily={FONT} fontSize={13.5} fontWeight={600} fill={INK}>
                {String(i + 1).padStart(2, "0")} {ph.name}
                <tspan fontWeight={400} fontSize={10.5} fill="#6f6d66" dx={8}>
                  {ph.decisions}
                </tspan>
              </text>
            )}

            {on ? (
              // the current phase, opened into its steps: back to front, each rising in after the last
              <g key={`open-${active}`}>
                {[2, 1, 0].map((j) => {
                  const st = ph.parts[j];
                  const y = y0 + j * (SD + SG);
                  return (
                    <g key={st.name} className="drop" style={{ animationDelay: `${(2 - j) * 80}ms` }}>
                      <Block x={0} y={y} w={W} d={SD} h={H_ON} tone="on" />
                      {st.kind.map((k, q) => (
                        <Tile key={k} x={12 + q * 13} y={y + 17} z={H_ON} kind={k} />
                      ))}
                      <text transform={flatX(st.kind.length > 1 ? 42 : 29, y + 20, H_ON)} fontFamily={FONT} fontSize={12.5} fill={INK}>
                        {st.name}
                      </text>
                      {st.d && (
                        <text transform={flatX(st.kind.length > 1 ? 42 : 29, y + 8, H_ON)} fontFamily={FONT} fontSize={9.5} fill="#8a887f">
                          {st.d}
                        </text>
                      )}
                    </g>
                  );
                })}
              </g>
            ) : (
              <g>
                <Block x={0} y={y0} w={W} d={D} h={H_OFF} tone={t} />
                {ph.kind.map((k, q) => (
                  <Tile key={k} x={14} y={y0 + 14 + q * 14} z={H_OFF} kind={k} faded={t === "next"} />
                ))}
                <text transform={flat(44, y0 + 14, H_OFF)} fontFamily={FONT} fontSize={15} fill={TONE[t].text} dy={6}>
                  {ph.name}
                </text>
              </g>
            )}
          </g>
        );
      })}
    </svg>
  );
}

/**
 * The pipeline, told by scrolling: on wide screens the section pins and each stretch of scroll advances
 * one phase; on narrow screens (or with reduced motion) it auto-advances and the tabs select a phase.
 */
export function Loop() {
  const n = PHASES.length;
  const ref = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(1);
  const [pinned, setPinned] = useState(false);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const update = () => setPinned(mq.matches && !still);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!pinned) {
      if (paused) return;
      const t = setInterval(() => setActive((a) => (a + 1) % n), 3600);
      return () => clearInterval(t);
    }
    let raf = 0;
    const frame = () => {
      raf = 0;
      const el = ref.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const total = r.height - window.innerHeight;
      const p = total > 0 ? Math.min(0.9999, Math.max(0, -r.top / total)) : 0;
      el.style.setProperty("--lp", p.toFixed(4));
      setActive(Math.floor(p * n));
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(frame);
    };
    frame();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      cancelAnimationFrame(raf);
    };
  }, [pinned, paused, n]);

  const select = (i: number) => {
    const el = ref.current;
    if (!pinned || !el) return setActive(i);
    const top = el.getBoundingClientRect().top + window.scrollY;
    const total = el.offsetHeight - window.innerHeight;
    window.scrollTo({ top: top + ((i + 0.5) / n) * total, behavior: "smooth" });
  };

  return (
    <div ref={ref} style={pinned ? { height: `${n * 85 + 60}vh` } : undefined}>
      <div
        className={pinned ? "sticky top-12 flex h-[calc(100vh-48px)] items-center" : ""}
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => setPaused(false)}
      >
        <div className="grid w-full gap-6 lg:grid-cols-[1.45fr_1fr] lg:items-center">
          <div className="cbox overflow-hidden bg-surface">
            <Diagram active={active} onSelect={select} />
            <div className="flex items-center justify-between border-t border-line px-4 py-2 font-mono text-[11px] text-t3">
              <span>
                {String(active + 1).padStart(2, "0")} / {String(n).padStart(2, "0")} · {PHASES[active].decisions}
              </span>
              <span className="flex gap-3">
                {(Object.keys(KIND) as Kind[]).map((k) => (
                  <span key={k} className="inline-flex items-center gap-1.5">
                    <span className="inline-block h-2 w-2 rounded-full border border-t2" style={{ background: KIND[k].color }} />
                    <span className="hidden sm:inline">{KIND[k].label}</span>
                  </span>
                ))}
              </span>
            </div>
          </div>

          <ol className="relative" role="tablist" aria-label="Pipeline phases">
            <span aria-hidden className="absolute bottom-3 left-[13px] top-3 w-px bg-line" />
            <span
              aria-hidden
              className="absolute left-[13px] top-3 w-px origin-top bg-t1 transition-[height] duration-500"
              style={{ height: `calc((100% - 24px) * ${active / (n - 1)})` }}
            />
            {PHASES.map((p, i) => {
              const on = i === active;
              return (
                <li key={p.name} className="relative pl-11">
                  <button
                    role="tab"
                    aria-selected={on}
                    onClick={() => select(i)}
                    className="group block w-full py-3 text-left"
                  >
                    <span
                      className={`absolute left-0 top-3 grid h-[27px] w-[27px] place-items-center border font-mono text-[11px] transition-colors duration-300 ${
                        i <= active ? "border-t1 bg-t1 text-surface" : "border-line bg-surface text-t3"
                      } ${on ? "!bg-mark !text-t1" : ""}`}
                    >
                      {i + 1}
                    </span>
                    <span className="flex items-baseline justify-between gap-3">
                      <span
                        className={`font-display text-[22px] font-medium tracking-[-0.02em] transition-colors duration-300 ${
                          on ? "text-t1" : "text-t4 group-hover:text-t2"
                        }`}
                      >
                        {p.name}
                      </span>
                      <span className={`font-mono text-[11px] transition-colors ${on ? "text-t3" : "text-t4"}`}>{p.decisions}</span>
                    </span>
                    <span className={`block font-mono text-[12px] transition-colors ${on ? "text-t3" : "text-t4"}`}>{p.steps}</span>
                    <span className={`grid transition-[grid-template-rows,opacity] duration-500 ${on ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"}`}>
                      <span className="overflow-hidden">
                        <span className="block pt-2 text-[14.5px] leading-[1.55] text-t2">{p.what}</span>
                        <span className="mt-2.5 flex flex-wrap gap-3">
                          {p.kind.map((k) => (
                            <span key={k} className="inline-flex items-center gap-1.5 font-mono text-[11px] text-t3">
                              <span className="inline-block h-2 w-2 rounded-full border border-t2" style={{ background: KIND[k].color }} />
                              {KIND[k].label}
                            </span>
                          ))}
                        </span>
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
            {pinned && (
              <li aria-hidden className="pl-11 pt-2 font-mono text-[10.5px] uppercase tracking-[0.06em] text-t4">
                {active < n - 1 ? "scroll to advance ↓" : "end of the loop ↓"}
              </li>
            )}
          </ol>
        </div>
      </div>
    </div>
  );
}
