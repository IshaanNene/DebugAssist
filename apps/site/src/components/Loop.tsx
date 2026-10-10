"use client";

import { useEffect, useState } from "react";

type Kind = "code" | "llm" | "clef";

interface Stage {
  name: string;
  kind: Kind[];
  decisions: string;
  what: string;
  parts: string[];
}

// The fixed plan (ADR 0001): always these steps, in this order.
const STAGES: Stage[] = [
  { name: "Ingest", kind: ["code"], decisions: "", what: "Pull the crash from Vitals or the rider's report from BugDrop, and pick the agent type for it.", parts: ["Vitals", "BugDrop"] },
  { name: "Triage", kind: ["code", "clef"], decisions: "D01 · D02", what: "Owner from CODEOWNERS, priority and severity, dedup against open issues, a ticket and a page.", parts: ["Owner", "Dedup", "Ticket"] },
  { name: "Context", kind: ["code", "clef"], decisions: "D03 · D04", what: "A deterministic evidence bundle from the MCP servers, scored for relevance and fitted to a budget.", parts: ["Logs", "Traces", "Commits"] },
  { name: "Root cause", kind: ["llm", "clef"], decisions: "D05 – D10", what: "An agent and its subagents explain the defect. Every claim cites an evidence id and is checked against it.", parts: ["Subagents", "Evidence", "Grounding"] },
  { name: "Mitigate", kind: ["code", "clef"], decisions: "D11", what: "A flag ↔ crash z-test; a rollback is proposed behind the policy gate, dry-run by default.", parts: ["z-test", "Rollback"] },
  { name: "Reproduce", kind: ["llm", "clef"], decisions: "D12 – D14", what: "Plan where, how and at which tier — then write a test that must fail on the shipped release.", parts: ["Unit", "Integration", "E2E"] },
  { name: "Fix", kind: ["llm"], decisions: "", what: "The smallest source change that makes the frozen reproduction, the suite and the repo's own CI pass.", parts: ["Sandbox", "Worktree"] },
  { name: "Validate", kind: ["code", "clef"], decisions: "D15", what: "Fails before, passes after, suite and CI green — or another attempt, up to three.", parts: ["Before", "After", "CI"] },
  { name: "Ship", kind: ["code", "clef"], decisions: "D16 · D17", what: "A pull request or a draft, by the evidence. After the deploy, watch the crash rate and resolve.", parts: ["PR", "Watch"] },
];

const KIND: Record<Kind, { label: string; color: string }> = {
  code: { label: "deterministic", color: "#cfcfc9" },
  llm: { label: "LLM agent", color: "#8b7cf0" },
  clef: { label: "Clef decision", color: "#e0901b" },
};

// Isometric projection: x runs down-right, y runs up-right, z is height.
const C = Math.cos(Math.PI / 6);
const S = Math.sin(Math.PI / 6);
const iso = (x: number, y: number, z = 0): [number, number] => [(x + y) * C, (x - y) * S - z];
const P = (...p: [number, number][]) => p.map(([a, b]) => `${a.toFixed(1)},${b.toFixed(1)}`).join(" ");

const W = 104; // slab width (x)
const D = 84; // slab depth (y)
const GAP = 20;
const STEP = D + GAP;
const INK = "#2f2e2a";
const FONT = "var(--font-geist-mono), ui-monospace, monospace";

/** Text lying flat on the top face, reading along the y axis (up-right). */
const flat = (x: number, y: number, z: number) => {
  const [tx, ty] = iso(x, y, z);
  return `matrix(${C} ${-S} ${C} ${S} ${tx} ${ty})`;
};

function Slab({
  x,
  y,
  w,
  d,
  h,
  z = 0,
  dim,
  top = "#fdfdfb",
}: {
  x: number;
  y: number;
  w: number;
  d: number;
  h: number;
  z?: number;
  dim?: boolean;
  top?: string;
}) {
  const t = [iso(x, y, z + h), iso(x, y + d, z + h), iso(x + w, y + d, z + h), iso(x + w, y, z + h)];
  const ink = dim ? "#a8a69e" : INK;
  const front = [iso(x + w, y, z + h), iso(x + w, y + d, z + h), iso(x + w, y + d, z), iso(x + w, y, z)];
  const left = [iso(x, y, z + h), iso(x + w, y, z + h), iso(x + w, y, z), iso(x, y, z)];
  return (
    <g>
      <polygon points={P(...left)} fill={dim ? "#f0f0ec" : "#ebebe6"} stroke={ink} strokeWidth={1} strokeLinejoin="round" />
      <polygon points={P(...front)} fill={dim ? "#e9e9e4" : "#dfdfd9"} stroke={ink} strokeWidth={1} strokeLinejoin="round" />
      <polygon points={P(...t)} fill={dim ? "#f8f8f5" : top} stroke={ink} strokeWidth={1.15} strokeLinejoin="round" />
    </g>
  );
}

export function Loop() {
  const [active, setActive] = useState(3);
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    if (paused) return;
    const t = setInterval(() => setActive((a) => (a + 1) % STAGES.length), 3200);
    return () => clearInterval(t);
  }, [paused]);

  const n = STAGES.length;
  const len = n * STEP - GAP;
  // the track under the slabs, extruded a little
  const tx0 = -18;
  const tx1 = W + 18;
  const ty0 = -18;
  const ty1 = len + 18;
  const th = 9;
  const trackTop = [iso(tx0, ty0, 0), iso(tx0, ty1, 0), iso(tx1, ty1, 0), iso(tx1, ty0, 0)];
  const trackFront = [iso(tx1, ty0, 0), iso(tx1, ty1, 0), iso(tx1, ty1, -th), iso(tx1, ty0, -th)];
  const trackLeft = [iso(tx0, ty0, 0), iso(tx1, ty0, 0), iso(tx1, ty0, -th), iso(tx0, ty0, -th)];

  // a faint drafting lattice on the ground plane
  const cells: [number, number][] = [];
  for (let gx = -320; gx <= 520; gx += 120) for (let gy = -260; gy <= len + 240; gy += 96) cells.push([gx, gy]);

  const st = STAGES[active];
  const ay = active * STEP;
  const parts = st.parts.map((p, k) => ({ p, x: W + 74 + (k % 2) * 8, y: ay - 40 + k * 70 }));

  // view box from the extremes of everything drawn
  // a fixed frame around every slab, the track and the farthest parts (so the view does not jump per step)
  const pts = [
    ...trackTop,
    iso(tx0, ty0, -th),
    iso(0, len, 90),
    iso(W + 74 + 8 + 60, -60, 0),
    iso(W + 74 + 8 + 60, len + 130, 0),
  ];
  const pad = 36;
  const minX = Math.min(...pts.map((p) => p[0])) - pad;
  const maxX = Math.max(...pts.map((p) => p[0])) + pad;
  const minY = Math.min(...pts.map((p) => p[1])) - pad;
  const maxY = Math.max(...pts.map((p) => p[1])) + pad;
  const vb = { x: minX, y: minY, w: maxX - minX, h: maxY - minY };

  return (
    <div onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
      <div className="cbox drafting overflow-hidden">
        <svg
          viewBox={`${vb.x.toFixed(0)} ${vb.y.toFixed(0)} ${vb.w.toFixed(0)} ${vb.h.toFixed(0)}`}
          className="block h-auto w-full select-none"
          role="img"
          aria-label={`The DebugAssist pipeline: ${STAGES.map((s) => s.name).join(", ")}. Showing ${st.name}.`}
        >
          <defs>
            <radialGradient id="fade" cx="50%" cy="55%" r="62%">
              <stop offset="55%" stopColor="#fff" />
              <stop offset="100%" stopColor="#000" />
            </radialGradient>
            <mask id="lattice-mask">
              <rect x={vb.x} y={vb.y} width={vb.w} height={vb.h} fill="url(#fade)" />
            </mask>
          </defs>
          <g mask="url(#lattice-mask)" stroke="#bfbdb4" strokeWidth={0.9} fill="none" opacity={0.75}>
            {cells.map(([gx, gy]) => (
              <polygon key={`${gx},${gy}`} points={P(iso(gx, gy), iso(gx, gy + 76), iso(gx + 96, gy + 76), iso(gx + 96, gy))} />
            ))}
          </g>

          {/* track */}
          <polygon points={P(...trackLeft)} fill="#dfe263" stroke={INK} strokeWidth={1} />
          <polygon points={P(...trackFront)} fill="#e8eb6a" stroke={INK} strokeWidth={1} />
          <polygon points={P(...trackTop)} fill="#f6f87e" stroke={INK} strokeWidth={1.1} />
          <text transform={flat(tx1 + 8, ty0 + 2, 0)} fontFamily={FONT} fontSize={13} fill="#4a4943" dy={14}>
            signal in
          </text>
          <text transform={flat(tx1 + 8, ty1 - 92, 0)} fontFamily={FONT} fontSize={13} fill="#4a4943" dy={14}>
            proof out
          </text>

          {/* connectors to the active stage's parts */}
          <g stroke={INK} strokeWidth={1.1} fill="none">
            {parts.map(({ p, x, y }) => {
              const a = iso(W, ay + D / 2, 0);
              const m = iso(W + 40, ay + D / 2, 0);
              const b = iso(W + 40, y + 28, 0);
              const c = iso(x, y + 28, 0);
              return <polyline key={p} points={P(a, m, b, c)} />;
            })}
          </g>

          {STAGES.map((s, i) => {
            const on = i === active;
            const y = i * STEP;
            const h = on ? 66 : 44;
            const z = on ? 14 : 0;
            return (
              <g key={s.name} onClick={() => setActive(i)} className="cursor-pointer">
                <Slab x={0} y={y} w={W} d={D} h={h} z={z} dim={!on} />
                <g>
                  <text transform={flat(16, y + 10, z + h)} fontFamily={FONT} fontSize={on ? 19 : 16} fill={on ? INK : "#8e8c85"} dy={18}>
                    {s.name}
                  </text>
                  {s.kind.map((k, j) => {
                    const [cx, cy] = iso(W - 18 - j * 14, y + D - 16, z + h);
                    return k === "code" ? null : (
                      <circle key={k} cx={cx} cy={cy} r={5} fill={KIND[k].color} stroke={on ? INK : "#a8a69e"} strokeWidth={0.9} opacity={on ? 1 : 0.55} />
                    );
                  })}
                </g>
              </g>
            );
          })}

          {parts.map(({ p, x, y }) => (
            <g key={`${active}-${p}`} style={{ animation: "none" }}>
              <Slab x={x} y={y} w={60} d={132} h={12} />
              <text transform={flat(x + 18, y + 16, 12)} fontFamily={FONT} fontSize={15} fill={INK} dy={16}>
                {p}
              </text>
            </g>
          ))}
        </svg>
      </div>

      <div className="cbox no-top -mt-px grid gap-0 md:grid-cols-[1fr_1.35fr]">
        <div className="border-b border-line p-5 md:border-b-0 md:border-r">
          <div className="font-mono text-[11px] uppercase tracking-[0.04em] text-t3">
            Step {active + 1} of {n}
            {st.decisions && <> · {st.decisions}</>}
          </div>
          <div className="mt-1.5 font-display text-[26px] font-medium tracking-[-0.02em]">{st.name}</div>
          <div className="mt-3 flex flex-wrap gap-3">
            {st.kind.map((k) => (
              <span key={k} className="inline-flex items-center gap-1.5 font-mono text-[11px] text-t3">
                <span className="inline-block h-2 w-2 rounded-full border border-t2" style={{ background: KIND[k].color }} />
                {KIND[k].label}
              </span>
            ))}
          </div>
        </div>
        <p className="p-5 text-[15px] leading-[1.55] text-t2" aria-live="polite">
          {st.what}
        </p>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5" role="tablist" aria-label="Pipeline steps">
        {STAGES.map((s, i) => (
          <button
            key={s.name}
            role="tab"
            aria-selected={i === active}
            onClick={() => setActive(i)}
            className={`h-7 border px-2.5 font-mono text-[11px] transition-colors ${
              i === active ? "border-t1 bg-t1 text-surface" : "border-line bg-surface text-t3 hover:border-line-strong hover:text-t2"
            }`}
          >
            {s.name}
          </button>
        ))}
      </div>
    </div>
  );
}
