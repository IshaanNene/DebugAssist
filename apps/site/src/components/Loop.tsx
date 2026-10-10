"use client";

import { useEffect, useRef, useState } from "react";

type Kind = "code" | "llm" | "clef";

interface Phase {
  name: string;
  steps: string;
  decisions: string;
  kind: Kind[];
  what: string;
  parts: string[];
}

// The fixed plan (ADR 0001) in four phases; the sub-phases are the pipeline's actual steps, always in this order.
const PHASES: Phase[] = [
  {
    name: "Detect",
    steps: "ingest · triage · dedup",
    decisions: "D01 · D02",
    kind: ["code", "clef"],
    what: "A crash from Vitals or a rider's report from BugDrop comes in. Owner from CODEOWNERS, priority and severity, dedup against open issues, a ticket and a page.",
    parts: ["Ingest", "Triage", "Dedup"],
  },
  {
    name: "Investigate",
    steps: "context · root cause · mitigate",
    decisions: "D03 – D11",
    kind: ["code", "llm", "clef"],
    what: "A deterministic evidence bundle from eleven MCP servers; an agent and its subagents explain the defect, every claim checked against its evidence; a flag rollback is proposed when the numbers say so.",
    parts: ["Context", "Root cause", "Mitigate"],
  },
  {
    name: "Fix",
    steps: "reproduce · fix · validate",
    decisions: "D12 – D15",
    kind: ["llm", "clef"],
    what: "A test that fails on the shipped release, the smallest fix that makes it pass, then proof: fails before, passes after, suite and CI green — or another attempt.",
    parts: ["Reproduce", "Fix", "Validate"],
  },
  {
    name: "Ship",
    steps: "ship gate · pull request · watch",
    decisions: "D16 · D17",
    kind: ["code", "clef"],
    what: "A pull request or a draft, decided by the evidence, linked from the ticket. After the deploy, watch the crash rate and resolve or reopen.",
    parts: ["Ship gate", "Pull request", "Watch"],
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

const INK = "#2f2e2a";
const FAINT = "#b9b7ae";
const FONT = "var(--font-geist-mono), ui-monospace, monospace";

// box geometry
const W = 118; // along x
const D = 128; // along y
const H = 66;
const GAP = 34;
const STEP = D + GAP;
// part slabs
const PW = 64;
const PD = 132;
const PH = 12;
const PGAP = 18;
const PX = W + 92; // parts sit in front of the boxes

function Block({ x, y, w, d, h, active }: { x: number; y: number; w: number; d: number; h: number; active: boolean }) {
  const ink = active ? INK : FAINT;
  const top = [iso(x, y, h), iso(x, y + d, h), iso(x + w, y + d, h), iso(x + w, y, h)];
  const front = [iso(x + w, y, h), iso(x + w, y + d, h), iso(x + w, y + d, 0), iso(x + w, y, 0)];
  const side = [iso(x, y, h), iso(x + w, y, h), iso(x + w, y, 0), iso(x, y, 0)];
  return (
    <g>
      <polygon points={P(...side)} fill={active ? "#e9e9e3" : "#f1f1ed"} stroke={ink} strokeWidth={1} strokeLinejoin="round" />
      <polygon points={P(...front)} fill={active ? "#dededa" : "#ebebe6"} stroke={ink} strokeWidth={1} strokeLinejoin="round" />
      <polygon points={P(...top)} fill={active ? "#ffffff" : "#f9f9f6"} stroke={ink} strokeWidth={1.2} strokeLinejoin="round" />
    </g>
  );
}

function Diagram({ active, onSelect }: { active: number; onSelect: (i: number) => void }) {
  const n = PHASES.length;
  const len = n * STEP - GAP;

  // track under the boxes
  const t0x = -22;
  const t1x = W + 22;
  const t0y = -40;
  const t1y = len + 40;
  const TH = 10;
  const trackTop = [iso(t0x, t0y), iso(t0x, t1y), iso(t1x, t1y), iso(t1x, t0y)];
  const trackFront = [iso(t1x, t0y), iso(t1x, t1y), iso(t1x, t1y, -TH), iso(t1x, t0y, -TH)];
  const trackEnd = [iso(t0x, t0y), iso(t1x, t0y), iso(t1x, t0y, -TH), iso(t0x, t0y, -TH)];

  // parts of the active phase: side by side along y, centred on its box, in front of the track
  const parts = (i: number) => {
    const k = PHASES[i].parts.length;
    const span = k * PD + (k - 1) * PGAP;
    const start = i * STEP + D / 2 - span / 2;
    return PHASES[i].parts.map((p, j) => ({ p, j, y: start + j * (PD + PGAP) }));
  };
  const cur = parts(active);
  const ay = active * STEP;

  // a fixed frame that fits every phase's parts, so the view never jumps
  const allParts = PHASES.flatMap((_, i) => parts(i));
  const ext = [
    ...trackTop,
    iso(t0x, t0y, -TH),
    iso(t1x, t0y, -TH),
    iso(0, len, H + 10),
    iso(0, 0, H + 10),
    iso(PX + PW, Math.min(...allParts.map((q) => q.y))),
    iso(PX + PW, Math.max(...allParts.map((q) => q.y)) + PD),
    iso(PX, Math.max(...allParts.map((q) => q.y)) + PD, PH),
  ];
  const pad = 30;
  const minX = Math.min(...ext.map((p) => p[0])) - pad;
  const maxX = Math.max(...ext.map((p) => p[0])) + pad;
  const minY = Math.min(...ext.map((p) => p[1])) - pad;
  const maxY = Math.max(...ext.map((p) => p[1])) + pad;

  // faint ground lattice
  const cells: [number, number][] = [];
  for (let gx = -460; gx <= PX + 360; gx += 150) for (let gy = -420; gy <= len + 420; gy += 170) cells.push([gx, gy]);

  // draw back (large y) to front
  const order = PHASES.map((_, i) => i).sort((a, b) => b - a);
  // the signal marker sits on the track, at the active phase
  const [mx, my] = iso(W + 11, ay + D / 2);
  const ease = "transform 0.6s cubic-bezier(0.2, 0.8, 0.2, 1)";

  return (
    <svg
      viewBox={`${minX.toFixed(0)} ${minY.toFixed(0)} ${(maxX - minX).toFixed(0)} ${(maxY - minY).toFixed(0)}`}
      className="block h-auto max-h-[64vh] w-full select-none"
      role="img"
      aria-label={`The DebugAssist pipeline in four phases: ${PHASES.map((p) => p.name).join(", ")}. Showing ${PHASES[active].name}.`}
    >
      <defs>
        <radialGradient id="lat-fade" cx="50%" cy="50%" r="60%">
          <stop offset="40%" stopColor="#fff" />
          <stop offset="100%" stopColor="#000" />
        </radialGradient>
        <mask id="lat-mask">
          <rect x={minX} y={minY} width={maxX - minX} height={maxY - minY} fill="url(#lat-fade)" />
        </mask>
      </defs>

      <g mask="url(#lat-mask)" fill="none" stroke="#dcdad2" strokeWidth={0.9}>
        {cells.map(([gx, gy]) => (
          <polygon key={`${gx},${gy}`} points={P(iso(gx, gy), iso(gx, gy + 130), iso(gx + 104, gy + 130), iso(gx + 104, gy))} />
        ))}
      </g>

      {/* track */}
      <polygon points={P(...trackEnd)} fill="#dde05f" stroke={INK} strokeWidth={1} />
      <polygon points={P(...trackFront)} fill="#e9ec6c" stroke={INK} strokeWidth={1} />
      <polygon points={P(...trackTop)} fill="#f7f985" stroke={INK} strokeWidth={1.1} />
      {/* moving dashes along the track: the signal flowing through */}
      <polyline
        className="flow"
        points={P(iso(W + 11, t0y + 10), iso(W + 11, t1y - 10))}
        fill="none"
        stroke={INK}
        strokeOpacity={0.35}
        strokeWidth={1}
        strokeDasharray="4 10"
      />
      <text transform={flat(t0x - 22, t0y + 4, 0)} fontFamily={FONT} fontSize={12} fill="#55544e">
        signal in
      </text>
      <text transform={flat(t1x - 40, t1y + 22, 0)} fontFamily={FONT} fontSize={12} fill="#55544e" dy={12}>
        proof out
      </text>

      {/* phase boxes, back to front; the active one lifts */}
      {order.map((i) => {
        const on = i === active;
        const y = i * STEP;
        return (
          <g
            key={PHASES[i].name}
            onClick={() => onSelect(i)}
            className="cursor-pointer"
            style={{ transform: on ? "translateY(-9px)" : "none", transition: ease }}
          >
            <Block x={0} y={y} w={W} d={D} h={H} active={on} />
            <g stroke={on ? INK : FAINT} strokeWidth={1}>
              {[0, 1, 2].map((t) => (
                <line key={t} x1={iso(12, y + 12 + t * 5, H)[0]} y1={iso(12, y + 12 + t * 5, H)[1]} x2={iso(26, y + 12 + t * 5, H)[0]} y2={iso(26, y + 12 + t * 5, H)[1]} />
              ))}
            </g>
            <text transform={flat(44, y + 14, H)} fontFamily={FONT} fontSize={16} fill={on ? INK : "#9a988f"} dy={6}>
              {PHASES[i].name}
            </text>
          </g>
        );
      })}

      {/* the signal marker */}
      <g style={{ transform: `translate(${mx.toFixed(1)}px, ${my.toFixed(1)}px)`, transition: ease }}>
        <circle r={9} fill="none" stroke={INK} strokeWidth={1} className="ping" />
        <polygon points={P([0, -5], [8, 0], [0, 5], [-8, 0])} fill={INK} />
      </g>

      {/* the active phase's parts: a small tree in front of its box, drawn in on every change */}
      <g key={`parts-${active}`}>
        <g fill="none" stroke={INK} strokeWidth={1.1}>
          <polyline className="draw" pathLength={1} points={P(iso(W + 11, ay + D / 2), iso(W + 40, ay + D / 2))} />
          <polyline className="draw" pathLength={1} points={P(iso(W + 40, cur[0].y + PD / 2), iso(W + 40, cur[cur.length - 1].y + PD / 2))} />
          {cur.map(({ p, y }) => (
            <polyline key={p} className="draw draw-late" pathLength={1} points={P(iso(W + 40, y + PD / 2), iso(PX, y + PD / 2))} />
          ))}
        </g>
        {[...cur].reverse().map(({ p, j, y }) => (
          <g key={p} className="drop" style={{ animationDelay: `${120 + j * 110}ms` }}>
            <Block x={PX} y={y} w={PW} d={PD} h={PH} active />
            <text transform={flat(PX + 22, y + 14, PH)} fontFamily={FONT} fontSize={13.5} fill={INK} dy={10}>
              {p}
            </text>
          </g>
        ))}
      </g>
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
