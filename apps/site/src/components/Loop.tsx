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

// who does the work, by colour: ink for code, violet for the LLM, amber for Clef
const KIND: Record<Kind, { label: string; color: string; swatch: string }> = {
  code: { label: "deterministic code", color: "var(--actor-code)", swatch: "bg-code" },
  llm: { label: "LLM agents", color: "var(--actor-llm)", swatch: "bg-llm" },
  clef: { label: "Clef decisions", color: "var(--actor-clef)", swatch: "bg-clef" },
};

const MONO = "var(--font-mono-src), ui-monospace, monospace";
const SANS = "var(--font-sans-src), Helvetica Neue, Arial, sans-serif";
const NS = { vectorEffect: "non-scaling-stroke" as const };
/** a step's fill, from its main actor: the same tints as the figures (Clef amber, LLM violet) */
const FILL: Record<Kind, string> = {
  code: "var(--raised)",
  llm: "color-mix(in srgb, var(--actor-llm) 17%, var(--raised))",
  clef: "color-mix(in srgb, var(--actor-clef) 22%, var(--raised))",
};

// geometry (viewBox units): the four phases in a row, the open one drawn out below as its three steps
const VW = 640;
const VH = 340;
const PW = 140;
const PG = 16;
const PY = 36;
const PH = 58;
const px = (i: number) => 16 + i * (PW + PG);
const DY = 150; // detail panel
const SW = 176;
const SG2 = 20;
const sx = (j: number) => 36 + j * (SW + SG2);
const SY = 196;
const SH = 100;

function Arrow({ x1, x2, y }: { x1: number; x2: number; y: number }) {
  return (
    <g>
      <line x1={x1} x2={x2 - 6} y1={y} y2={y} stroke="var(--line-strong)" strokeWidth={1} {...NS} />
      <polygon points={`${x2},${y} ${x2 - 7},${y - 3.5} ${x2 - 7},${y + 3.5}`} fill="var(--line-strong)" />
    </g>
  );
}

function Diagram({ active, onSelect }: { active: number; onSelect: (i: number) => void }) {
  const ph = PHASES[active];
  const ax = px(active);
  return (
    <svg
      viewBox={`0 0 ${VW} ${VH}`}
      className="block h-auto w-full select-none"
      role="img"
      aria-label={`The DebugAssist pipeline in four phases: ${PHASES.map((p) => p.name).join(", ")}. Showing ${ph.name}: ${ph.parts.map((s) => s.name).join(", ")}.`}
    >
      <text x={16} y={22} fontFamily={MONO} fontSize={10} fill="var(--fg-3)">
        signal in
      </text>
      <text x={VW - 16} y={22} textAnchor="end" fontFamily={MONO} fontSize={10} fill="var(--fg-3)">
        proof out
      </text>

      {/* the open phase, drawn out: a callout from its box to the panel of its steps */}
      <path d={`M${ax} ${PY + PH} L16 ${DY} M${ax + PW} ${PY + PH} L${VW - 16} ${DY}`} fill="none" stroke="var(--line-2)" strokeDasharray="3 4" {...NS} />
      <rect x={16} y={DY} width={VW - 32} height={VH - DY - 16} fill="var(--raised)" stroke="var(--line-2)" {...NS} />
      <text x={36} y={DY + 26} fontFamily={MONO} fontSize={10.5} fill="var(--fg-3)" letterSpacing="0.06em">
        {String(active + 1).padStart(2, "0")} · {ph.name.toUpperCase()} · {ph.decisions}
      </text>

      {PHASES.map((p, i) => {
        const on = i === active;
        const done = i < active;
        return (
          <g key={p.name} onClick={() => onSelect(i)} className="cursor-pointer">
            <rect
              x={px(i)}
              y={PY}
              width={PW}
              height={PH}
              fill={on ? "var(--mark)" : done ? "var(--raised)" : "var(--bg)"}
              stroke={on || done ? "var(--fg)" : "var(--line-2)"}
              strokeWidth={on ? 1.4 : 1}
              strokeDasharray={on || done ? undefined : "4 3"}
              {...NS}
            />
            <text x={px(i) + 12} y={PY + 24} fontFamily={SANS} fontSize={14} fontWeight={500} fill={on || done ? "var(--fg)" : "var(--fg-4)"}>
              {p.name}
            </text>
            <text x={px(i) + 12} y={PY + 43} fontFamily={MONO} fontSize={9.5} fill={on ? "var(--fg-2)" : "var(--fg-4)"}>
              {p.decisions}
            </text>
            {p.kind.map((k, q) => (
              <rect key={k} x={px(i) + PW - 14 - q * 12} y={PY + 10} width={8} height={8} fill={KIND[k].color} stroke="var(--fg)" strokeWidth={0.8} {...NS} />
            ))}
            {i < PHASES.length - 1 && <Arrow x1={px(i) + PW} x2={px(i + 1)} y={PY + PH / 2} />}
          </g>
        );
      })}

      <g key={`open-${active}`}>
        {ph.parts.map((st, j) => (
          <g key={st.name}>
            <rect x={sx(j)} y={SY} width={SW} height={SH} fill={FILL[st.kind[0]]} stroke={st.kind[0] === "code" ? "var(--fg)" : KIND[st.kind[0]].color} strokeWidth={1.3} {...NS} />
            <text x={sx(j) + 14} y={SY + 28} fontFamily={SANS} fontSize={15} fontWeight={500} fill="var(--fg)">
              {st.name}
            </text>
            <text x={sx(j) + 14} y={SY + 48} fontFamily={MONO} fontSize={10} fill="var(--fg-3)">
              {st.d ?? "no decision"}
            </text>
            {st.kind.map((k, q) => (
              <g key={k}>
                <rect x={sx(j) + 14} y={SY + 66 + q * 16} width={9} height={9} fill={KIND[k].color} stroke="var(--fg)" strokeWidth={0.8} {...NS} />
                <text x={sx(j) + 30} y={SY + 74 + q * 16} fontFamily={MONO} fontSize={9.5} fill="var(--fg-2)">
                  {KIND[k].label}
                </text>
              </g>
            ))}
            {j < 2 && <Arrow x1={sx(j) + SW} x2={sx(j + 1)} y={SY + SH / 2} />}
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
        className={pinned ? "sticky top-14 flex h-[calc(100vh-56px)] items-center" : ""}
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
                    <span className={`inline-block h-2.5 w-2.5 border border-t1 ${KIND[k].swatch}`} />
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
                              <span className={`inline-block h-2.5 w-2.5 border border-t1 ${KIND[k].swatch}`} />
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
