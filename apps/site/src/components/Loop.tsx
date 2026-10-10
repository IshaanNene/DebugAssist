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

// The fixed plan (ADR 0001): always these steps, in this order. Kinds: deterministic code, LLM agents, Clef.
const STAGES: Stage[] = [
  { name: "Ingest", kind: ["code"], decisions: "", what: "Pull the crash from Vitals or the rider's report from BugDrop; pick the agent type.", parts: ["Vitals", "BugDrop", "agent type"] },
  { name: "Triage", kind: ["code", "clef"], decisions: "D01 · D02", what: "Owner from CODEOWNERS, priority, dedup against open issues, a ticket and a page.", parts: ["CODEOWNERS", "dedup", "Jira"] },
  { name: "Context", kind: ["code", "clef"], decisions: "D03 · D04", what: "A deterministic evidence bundle from the MCP servers, scored and fitted to a budget.", parts: ["logs", "traces", "flags", "commits"] },
  { name: "Root cause", kind: ["llm", "clef"], decisions: "D05 – D10", what: "An agent and subagents explain the defect; every claim cites an evidence id and is checked.", parts: ["subagents", "evidence ids", "grounding"] },
  { name: "Mitigate", kind: ["code", "clef"], decisions: "D11", what: "Flag ↔ crash z-test; a rollback is proposed behind the policy gate.", parts: ["z-test", "rollback", "policy"] },
  { name: "Reproduce", kind: ["llm", "clef"], decisions: "D12 – D14", what: "Plan where, how and at which tier; the test must fail on the shipped release.", parts: ["unit", "integration", "e2e"] },
  { name: "Fix", kind: ["llm"], decisions: "", what: "The smallest source change that makes the frozen reproduction and the suite pass.", parts: ["sandbox", "worktree", "lint"] },
  { name: "Validate", kind: ["code", "clef"], decisions: "D15", what: "Fails before, passes after, suite and CI green — or retry, up to three attempts.", parts: ["before", "after", "CI"] },
  { name: "Ship", kind: ["code", "clef"], decisions: "D16 · D17", what: "PR or draft by the evidence; after the deploy, watch the crash rate and resolve.", parts: ["PR", "ticket", "watch"] },
];

const C = Math.cos(Math.PI / 6);
const S = Math.sin(Math.PI / 6);
const iso = (x: number, y: number, z = 0): [number, number] => [(x - y) * C, (x + y) * S - z];
const pts = (...p: [number, number][]) => p.map(([a, b]) => `${a.toFixed(1)},${b.toFixed(1)}`).join(" ");

const KIND_LABEL: Record<Kind, string> = { code: "deterministic", llm: "LLM agent", clef: "Clef decision" };

const W = 112; // box size along x
const D = 96; // depth along y
const STEP_X = 62;
const STEP_Y = -150; // boxes climb up and to the right
const origin = (i: number): [number, number] => [i * STEP_X, i * STEP_Y];

function Box({ i, active, onPick }: { i: number; active: boolean; onPick: () => void }) {
  const [x0, y0] = origin(i);
  const h = active ? 58 : 34;
  const z = active ? 26 : 0;
  const top = [iso(x0, y0, z + h), iso(x0 + W, y0, z + h), iso(x0 + W, y0 + D, z + h), iso(x0, y0 + D, z + h)];
  const left = [iso(x0, y0 + D, z + h), iso(x0 + W, y0 + D, z + h), iso(x0 + W, y0 + D, z), iso(x0, y0 + D, z)];
  const right = [iso(x0 + W, y0, z + h), iso(x0 + W, y0 + D, z + h), iso(x0 + W, y0 + D, z), iso(x0 + W, y0, z)];
  const [tx, ty] = iso(x0 + 22, y0 + D - 20, z + h);  // along the edge that climbs, like the track
  const st = STAGES[i];
  return (
    <g onMouseEnter={onPick} onClick={onPick} style={{ cursor: "pointer", transition: "transform .35s" }}>
      <polygon points={pts(...left)} fill="#ebe9e2" stroke="#2c2b27" strokeWidth={1.1} />
      <polygon points={pts(...right)} fill="#e2dfd6" stroke="#2c2b27" strokeWidth={1.1} />
      <polygon points={pts(...top)} fill={active ? "#fdfdf6" : "#f9f8f3"} stroke="#2c2b27" strokeWidth={1.3} />
      <text
        transform={`matrix(${C} ${-S} ${C} ${S} ${tx} ${ty})`}
        fontFamily="var(--font-mono-face)"
        fontSize={active ? 17 : 15}
        fill="#1d1d1a"
      >
        {st.name}
      </text>
      {st.kind.includes("clef") && (
        <circle cx={iso(x0 + W - 14, y0 + D - 14, z + h)[0]} cy={iso(x0 + W - 14, y0 + D - 14, z + h)[1]} r={5.5} fill="#f59e0b" stroke="#2c2b27" strokeWidth={0.8} />
      )}
      {st.kind.includes("llm") && (
        <circle cx={iso(x0 + W - 26, y0 + D - 14, z + h)[0]} cy={iso(x0 + W - 26, y0 + D - 14, z + h)[1]} r={5.5} fill="#a78bfa" stroke="#2c2b27" strokeWidth={0.8} />
      )}
    </g>
  );
}

export function Loop() {
  const [active, setActive] = useState(3);
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    if (paused) return;
    const t = setInterval(() => setActive((a) => (a + 1) % STAGES.length), 2600);
    return () => clearInterval(t);
  }, [paused]);
  const n = STAGES.length;
  // the track: a band under every box, from the signal in to the proof out
  const [lx, ly] = origin(n - 1);
  const a = iso(-24, D + 26, 0);
  const b = iso(lx + W + 24, ly + D + 26, 0);
  const c = iso(lx + W + 24, ly - 26, 0);
  const d = iso(-24, -26, 0);
  const all = [a, b, c, d, ...STAGES.map((_, i) => iso(origin(i)[0], origin(i)[1], 90))];
  const minX = Math.min(...all.map((p) => p[0])) - 20;
  const maxX = Math.max(...all.map((p) => p[0])) + 20;
  const minY = Math.min(...all.map((p) => p[1])) - 20;
  const maxY = Math.max(...all.map((p) => p[1])) + 20;
  const st = STAGES[active];
  return (
    <div className="space-y-8" onMouseLeave={() => setPaused(false)}>
      <svg
        viewBox={`${minX.toFixed(0)} ${minY.toFixed(0)} ${(maxX - minX).toFixed(0)} ${(maxY - minY).toFixed(0)}`}
        className="w-full h-auto select-none"
        role="img"
        aria-label="The DebugAssist pipeline as nine stages from ingest to ship"
        onMouseEnter={() => setPaused(true)}
      >
        <polygon points={pts(a, b, c, d)} fill="var(--mark)" fillOpacity={0.55} stroke="#2c2b27" strokeWidth={1} />
        <text transform={`matrix(${C} ${-S} ${C} ${S} ${a[0] + 10} ${a[1] + 18})`} fontFamily="var(--font-mono-face)" fontSize={15} fill="#3b3a35">
          signal in
        </text>
        <text transform={`matrix(${C} ${-S} ${C} ${S} ${b[0] - 120} ${b[1] + 18})`} fontFamily="var(--font-mono-face)" fontSize={15} fill="#3b3a35">
          proof out
        </text>
        {STAGES.map((_, i) => (
          <Box key={i} i={i} active={i === active} onPick={() => setActive(i)} />
        ))}
      </svg>
      <div className="frame p-5 max-w-2xl" aria-live="polite">
        <span className="frame-corners" />
        <div className="font-mono text-xs uppercase tracking-wider text-muted">
          step {active + 1} of {n}
          {st.decisions && <> · {st.decisions}</>}
        </div>
        <h3 className="mt-1 text-2xl font-semibold">{st.name}</h3>
        <p className="mt-2 text-ink-2 leading-relaxed">{st.what}</p>
        <div className="mt-4 flex flex-wrap gap-2">
          {st.parts.map((p) => (
            <span key={p} className="font-mono text-xs border border-line bg-panel px-2 py-1">
              {p}
            </span>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap gap-3 text-xs text-muted font-mono">
          {st.kind.map((k) => (
            <span key={k} className="inline-flex items-center gap-1.5">
              <span
                className="inline-block w-2.5 h-2.5 rounded-full border border-ink-2"
                style={{ background: k === "clef" ? "#f59e0b" : k === "llm" ? "#a78bfa" : "#d8d5cb" }}
              />
              {KIND_LABEL[k]}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
