"use client";

import { useState } from "react";

// The system as four isometric plates, bottom (what breaks) to top (what acts). The plates pull apart as the
// section scrolls through the viewport (`--p` from the Motion observer); hovering a layer in the legend lifts it.

const C = Math.cos(Math.PI / 6);
const S = Math.sin(Math.PI / 6);
const iso = (x: number, y: number, z = 0): [number, number] => [(x + y) * C, (x - y) * S - z];
const P = (...p: [number, number][]) => p.map(([a, b]) => `${a.toFixed(1)},${b.toFixed(1)}`).join(" ");

const INK = "#2f2e2a";
const SOFT = "#8a887f";
const FONT = "var(--font-geist-mono), ui-monospace, monospace";

/** Text lying on a horizontal face at height z, reading along +x (lines stack towards −y). */
const flatX = (x: number, y: number, z: number) => {
  const [tx, ty] = iso(x, y, z);
  return `matrix(${C} ${S} ${-C} ${S} ${tx.toFixed(1)} ${ty.toFixed(1)})`;
};

// plate geometry: plates are long along x; blocks sit in a row along x
const LX = 620;
const LY = 150;
const T = 9;
const BY0 = 30; // blocks span y ∈ [BY0, LY - 14]
const BH = 24;
const BGAP = 12;
const MARGIN = 20;
// the fan: layer k sits k·STEP behind (+y) and k·RISE higher than the one below, scaled by scroll (--p)
const STEP0 = 0;
const STEP1 = LY + 26;
const RISE0 = 30;
const RISE1 = 24;

interface Layer {
  name: string;
  blurb: string;
  blocks: [string, string][];
  plate: string;
}

function layers(servers: number, tools: number): Layer[] {
  return [
    {
      name: "Target system",
      blurb:
        "MiniRide, the app the bugs live in: a React rider app, a Node GraphQL gateway, dispatch in Python and payments in Go, with feature flags from Unleash.",
      blocks: [
        ["client", "React"],
        ["gateway", "Node · GraphQL"],
        ["dispatch", "Python"],
        ["payments", "Go"],
        ["flags", "Unleash"],
      ],
      plate: "#f9f9f6",
    },
    {
      name: "Signals",
      blurb:
        "How problems surface: Vitals for crashes and performance, BugDrop for rider reports with screenshots and logs, and OpenTelemetry into Jaeger, Loki and Prometheus.",
      blocks: [
        ["Vitals", "crashes · perf"],
        ["BugDrop", "rider reports"],
        ["traces", "Jaeger"],
        ["logs", "Loki"],
        ["metrics", "Prometheus"],
      ],
      plate: "#f9f9f6",
    },
    {
      name: "Evidence",
      blurb: `${servers} MCP servers, ${tools} tools — the only way agents see the world. Each returns structured evidence with an id that claims must cite.`,
      blocks: [
        ["crashes", "Vitals · BugDrop"],
        ["code", "search · git"],
        ["telemetry", "logs · traces"],
        ["flags", "releases"],
        ["tickets", "Jira · incidents"],
      ],
      plate: "#f9f9f6",
    },
    {
      name: "Agent core",
      blurb:
        "LangGraph runs the fixed plan; Clef makes each judgement call; LLM agents reason and write code in a network-less sandbox; a policy gate stands before every write.",
      blocks: [
        ["LangGraph", "fixed plan"],
        ["Clef", "decisions"],
        ["agents", "LLM · skills"],
        ["sandbox", "no network"],
        ["policy gate", "→ PR · ticket"],
      ],
      plate: "#f7f985",
    },
  ];
}

function Box3({ x, y, z, w, d, h, top, side, front, stroke = INK }: { x: number; y: number; z: number; w: number; d: number; h: number; top: string; side: string; front: string; stroke?: string }) {
  const tp = [iso(x, y, z + h), iso(x, y + d, z + h), iso(x + w, y + d, z + h), iso(x + w, y, z + h)];
  const fr = [iso(x + w, y, z + h), iso(x + w, y + d, z + h), iso(x + w, y + d, z), iso(x + w, y, z)];
  const sd = [iso(x, y, z + h), iso(x + w, y, z + h), iso(x + w, y, z), iso(x, y, z)];
  return (
    <g strokeLinejoin="round">
      <polygon points={P(...sd)} fill={side} stroke={stroke} strokeWidth={1} />
      <polygon points={P(...fr)} fill={front} stroke={stroke} strokeWidth={1} />
      <polygon points={P(...tp)} fill={top} stroke={stroke} strokeWidth={1.1} />
    </g>
  );
}

export function Architecture({ servers, tools }: { servers: number; tools: number }) {
  const L = layers(servers, tools);
  const [hover, setHover] = useState<number | null>(null);
  const n = L.length;
  const nb = L[0].blocks.length;
  const bw = (LX - 2 * MARGIN - (nb - 1) * BGAP) / nb;
  const mid = (n - 1) / 2;

  // frame: fully fanned out, layers centred on the middle of the stack
  const open = (k: number) => ({ y: (k - mid) * STEP1, z: (k - mid) * (RISE0 + RISE1) });
  const ext = [0, n - 1].flatMap((k) => {
    const o = open(k);
    return [iso(0, o.y, o.z + BH), iso(LX, o.y, o.z - T), iso(0, o.y + LY, o.z + BH), iso(LX, o.y + LY, o.z), iso(LX, o.y, o.z + BH)];
  });
  const pad = 24;
  const minX = Math.min(...ext.map((p) => p[0])) - pad;
  const maxX = Math.max(...ext.map((p) => p[0])) + pad;
  const minY = Math.min(...ext.map((p) => p[1])) - pad - 8;
  const maxY = Math.max(...ext.map((p) => p[1])) + pad;

  return (
    <div data-scrub="0.95,1.05">
      <div className="cbox overflow-hidden bg-surface">
        <svg
          viewBox={`${minX.toFixed(0)} ${minY.toFixed(0)} ${(maxX - minX).toFixed(0)} ${(maxY - minY).toFixed(0)}`}
          className="block h-auto max-h-[78vh] w-full select-none"
          role="img"
          aria-label={`DebugAssist architecture in four layers, bottom to top: ${L.map((l) => l.name).join(", ")}.`}
        >
          {L.map((layer, k) => {
            const on = hover === k;
            const dim = hover !== null && !on;
            // move along +y (screen: right and up) and lift in z, both growing with scroll
            const f = k - mid;
            const step = `(${STEP0} + ${STEP1} * var(--p, 1)) * ${f}`;
            const rise = `(${RISE0} + ${RISE1} * var(--p, 1)) * ${f}`;
            const tx = `calc(${C.toFixed(4)}px * ${step})`;
            const ty = `calc(${(-S).toFixed(4)}px * ${step} - 1px * ${rise} - ${on ? 12 : 0}px)`;
            return (
              <g
                key={layer.name}
                style={{
                  transform: `translate(${tx}, ${ty})`,
                  transition: "transform 0.45s cubic-bezier(0.2, 0.8, 0.2, 1), opacity 0.3s",
                  opacity: dim ? 0.4 : 1,
                }}
                onMouseEnter={() => setHover(k)}
                onMouseLeave={() => setHover(null)}
              >
                <Box3
                  x={0}
                  y={0}
                  z={-T}
                  w={LX}
                  d={LY}
                  h={T}
                  top={on ? "#fbff7a" : layer.plate}
                  side={layer.plate === "#f9f9f6" ? "#e6e6df" : "#dde05f"}
                  front={layer.plate === "#f9f9f6" ? "#ebebe5" : "#e9ec6c"}
                />
                <text transform={flatX(MARGIN, 8, 0)} fontFamily={FONT} fontSize={11} fill={INK} letterSpacing="0.06em" dy={4}>
                  {String(k + 1).padStart(2, "0")} · {layer.name.toUpperCase()}
                </text>

                {/* blocks: the row runs along x; draw back (small x) to front */}
                {layer.blocks.map(([label, sub], j) => {
                  const x = MARGIN + j * (bw + BGAP);
                  return (
                    <g key={label}>
                      <Box3 x={x} y={BY0} z={0} w={bw} d={LY - 14 - BY0} h={BH} top="#ffffff" side="#e9e9e3" front="#dededa" />
                      <text transform={flatX(x + 10, LY - 40, BH)} fontFamily={FONT} fontSize={13} fill={INK}>
                        {label}
                      </text>
                      <text transform={flatX(x + 10, LY - 64, BH)} fontFamily={FONT} fontSize={9.5} fill={SOFT}>
                        {sub}
                      </text>
                    </g>
                  );
                })}
              </g>
            );
          })}
        </svg>
        <div className="flex items-center justify-between border-t border-line px-4 py-2 font-mono text-[11px] text-t3">
          <span>signals rise from the app · actions leave through the policy gate</span>
          <span className="hidden sm:inline">hover a layer</span>
        </div>
      </div>

      <ol className="cbox no-top -mt-px grid gap-px bg-line sm:grid-cols-2 lg:grid-cols-4">
        {L.map((layer, k) => {
          const on = hover === k;
          return (
            <li
              key={layer.name}
              className={`fx relative cursor-default p-5 transition-colors ${on ? "bg-[#fdfde6]" : "bg-surface"}`}
              style={{ ["--i" as string]: k }}
              onMouseEnter={() => setHover(k)}
              onMouseLeave={() => setHover(null)}
            >
              <div className="flex items-center gap-2.5">
                <span
                  className={`grid h-[24px] w-[24px] place-items-center border font-mono text-[11px] transition-colors duration-300 ${
                    on ? "border-t1 bg-mark text-t1" : k === n - 1 ? "border-t1 bg-t1 text-surface" : "border-line bg-surface text-t3"
                  }`}
                >
                  {k + 1}
                </span>
                <span className="font-display text-[19px] font-medium tracking-[-0.02em] text-t1">{layer.name}</span>
              </div>
              <p className="mt-2.5 text-[13.5px] leading-[1.55] text-t3">{layer.blurb}</p>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
