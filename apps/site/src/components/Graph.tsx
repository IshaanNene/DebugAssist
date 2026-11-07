"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

// The pipeline exactly as packages/pipeline/src/debugassist/pipeline/graph.py builds it: ten nodes, always in this
// order, with two branches the graph really has — validate → fix (D15 retry) and the root cause routing a bug away
// ("not ours") — and any step may stop the run. Node kinds follow NODE_KIND; decisions follow the templates' stage.

type Kind = "code" | "llm" | "clef";
interface Node {
  id: string;
  name: string;
  kinds: Kind[];
  what: string;
  decisions: [string, string][];
}

const NODES: Node[] = [
  { id: "ingest", name: "Ingest", kinds: ["code"], what: "A crash from Vitals, a rider’s report from BugDrop or a labeled GitHub issue becomes one incident.", decisions: [] },
  { id: "auto_triage", name: "Triage", kinds: ["code", "clef"], what: "Owner from CODEOWNERS, priority and severity, a duplicate check against open issues, then a ticket and a page.", decisions: [["D01", "triage"], ["D02", "dedup"]] },
  { id: "context_collector", name: "Context", kinds: ["code", "clef"], what: "A deterministic evidence bundle from the MCP servers: crashes, code, git history, flags and telemetry.", decisions: [["D03", "log relevance"], ["D04", "screenshots"]] },
  { id: "classify_rca", name: "Root cause", kinds: ["llm", "clef"], what: "An agent and its subagents explain the defect. Every claim is checked against the evidence it cites.", decisions: [["D05", "categorize"], ["D06", "more evidence"], ["D07", "fan-out"], ["D08", "rabbit hole"], ["D09", "grounding"], ["D10", "model routing"]] },
  { id: "mitigate", name: "Mitigate", kinds: ["code", "clef"], what: "Roll back a feature flag when the numbers say so — and only with approval.", decisions: [["D11", "mitigation"]] },
  { id: "fix", name: "Fix", kinds: ["llm", "clef"], what: "A test that fails on the shipped release, then the smallest change that makes it pass.", decisions: [["D12", "localization"], ["D13", "fix strategy"]] },
  { id: "validate", name: "Validate", kinds: ["code", "clef"], what: "Fails before, passes after; the suite and CI are green. If not, back to Fix.", decisions: [["D14", "validation tier"], ["D15", "retry"]] },
  { id: "ship_gate", name: "Ship gate", kinds: ["clef"], what: "A pull request or a draft, decided from the evidence — or nothing at all.", decisions: [["D16", "ship gate"]] },
  { id: "pr_and_notify", name: "Pull request", kinds: ["code"], what: "Push a debugassist/* branch, open the pull request, link the ticket and tell the channel.", decisions: [] },
  { id: "post_merge_watch", name: "Watch", kinds: ["code", "clef"], what: "After the deploy, watch the crash rate. Resolve the issue, or reopen it.", decisions: [["D17", "post-merge"], ["D18", "feedback"]] },
];

const LABEL: Record<Kind, string> = { code: "code", llm: "LLM", clef: "Clef" };

// layout: two rows of five, in a 1200 × 400 box
const W = 1200;
const H = 400;
const NW = 196;
const NH = 104;
const X = [0, 251, 502, 753, 1004];
const Y = [64, 236];
const pos = (i: number) => ({ x: X[i % 5], y: Y[Math.floor(i / 5)] });

// Right-angle edges: the two rows, the return from Mitigate down to Fix, the D15 retry loop under Validate → Fix,
// and the root cause routing a bug away above the top row.
const cxn = (i: number) => X[i] + NW / 2;
const MID = (Y[0] + NH + Y[1]) / 2;
const LOOP = Y[1] + NH + 34;
const EDGES: { d: string; dashed?: boolean }[] = [
  ...[0, 1, 2, 3].map((i) => ({ d: `M${X[i] + NW} ${Y[0] + NH / 2} H ${X[i + 1]}` })),
  { d: `M${cxn(4)} ${Y[0] + NH} V ${MID} H ${cxn(0)} V ${Y[1]}` },
  ...[0, 1, 2, 3].map((i) => ({ d: `M${X[i] + NW} ${Y[1] + NH / 2} H ${X[i + 1]}` })),
  { d: `M${cxn(1)} ${Y[1] + NH} V ${LOOP} H ${cxn(0)} V ${Y[1] + NH}`, dashed: true },
  { d: `M${cxn(3)} ${Y[0]} V 22 H ${X[4] - 6}`, dashed: true },
];

export function Graph({ ms, runLabel }: { ms: Record<string, number>; runLabel: string }) {
  const [sel, setSel] = useState(3);
  const [auto, setAuto] = useState(true);
  const box = useRef<HTMLDivElement>(null);

  // walk the graph on its own until someone picks a node, and only while it is on screen
  useEffect(() => {
    if (!auto || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let visible = false;
    const io = new IntersectionObserver(([e]) => (visible = e.isIntersecting), { threshold: 0.3 });
    if (box.current) io.observe(box.current);
    const t = setInterval(() => {
      if (visible) setSel((s) => (s + 1) % NODES.length);
    }, 2600);
    return () => {
      clearInterval(t);
      io.disconnect();
    };
  }, [auto]);

  const pick = (i: number) => {
    setAuto(false);
    setSel(i);
  };
  const n = NODES[sel];
  const total = Object.values(ms).reduce((a, b) => a + b, 0);

  return (
    <div ref={box}>
      {/* desktop graph */}
      <div className="relative hidden aspect-[1200/400] w-full xl:block">
        <svg viewBox={`0 0 ${W} ${H}`} className="absolute inset-0 h-full w-full overflow-visible" aria-hidden>
          <defs>
            <marker id="ga" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
              <path d="M0 0 L8 4 L0 8 z" fill="var(--line-strong)" />
            </marker>
          </defs>
          {EDGES.map((e, i) => (
            <g key={i}>
              <path d={e.d} fill="none" stroke="var(--line-strong)" strokeWidth={1} strokeDasharray={e.dashed ? "4 4" : undefined} markerEnd="url(#ga)" />
            </g>
          ))}
        </svg>
        <Label x={(cxn(0) + cxn(1)) / 2} y={LOOP}>retry · D15</Label>
        <Label x={X[4]} y={22} left>
          not ours → report, route
        </Label>
        {NODES.map((node, i) => {
          const p = pos(i);
          return (
            <div key={node.id} className="absolute" style={{ left: `${(p.x / W) * 100}%`, top: `${(p.y / H) * 100}%`, width: `${(NW / W) * 100}%`, height: `${(NH / H) * 100}%` }}>
              <NodeButton node={node} i={i} on={i === sel} onPick={pick} ms={ms[node.id]} />
            </div>
          );
        })}
      </div>

      {/* phones: a list in two columns */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5 xl:hidden">
        {NODES.map((node, i) => (
          <div key={node.id} className="h-[92px]">
            <NodeButton node={node} i={i} on={i === sel} onPick={pick} ms={ms[node.id]} />
          </div>
        ))}
      </div>

      {/* the selected node, in detail */}
      <div className="panel mt-6 grid gap-6 p-6 md:grid-cols-[1.25fr_1fr] md:p-7" aria-live="polite">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <span className="font-mono text-[12px] text-t4">{String(sel + 1).padStart(2, "0")} / 10</span>
            <h3 className="title text-[28px] text-t1">{n.name}</h3>
  <code className=" border border-line bg-sunk/60 px-2 py-0.5 font-mono text-[11.5px] text-t3">{n.id}</code>
          </div>
          <p className="mt-3 max-w-[56ch] text-[15.5px] leading-[1.6] text-t2">{n.what}</p>
          <p className="mt-4 font-mono text-[12px] text-t3">
            acts: <span className="text-t1">{n.kinds.map((k) => LABEL[k]).join(" + ")}</span>
          </p>
        </div>
        <div className="grid content-start gap-4">
          <div>
            <div className="label text-[10.5px] text-t4">Clef decisions here</div>
            {n.decisions.length ? (
              <ul className="mt-2 flex flex-wrap gap-1.5">
                {n.decisions.map(([d, name]) => (
  <li key={d} className="inline-flex items-center gap-1.5 border border-line-2 bg-surface px-2.5 py-1 font-mono text-[11.5px] text-t2">
                    <span className="text-t1">{d}</span> {name}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 font-mono text-[12px] text-t3">none — deterministic</p>
            )}
          </div>
          <div>
            <div className="label text-[10.5px] text-t4">In {runLabel}</div>
            {ms[n.id] !== undefined ? (
              <p className="mt-2 font-mono text-[12px] text-t3">
                <span className="text-t1">{fmt(ms[n.id])}</span> · {Math.max(1, Math.round((ms[n.id] / total) * 100))}% of the run’s step time
              </p>
            ) : (
              <p className="mt-2 font-mono text-[12px] text-t3">not reached — this run stopped after validate</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function NodeButton({ node, i, on, onPick, ms }: { node: Node; i: number; on: boolean; onPick: (i: number) => void; ms?: number }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={() => onPick(i)}
  className="gnode flex h-full w-full flex-col justify-between border border-line bg-surface p-3.5 text-left"
    >
      <div className="flex items-center justify-between">
        <span className="font-mono text-[10.5px] text-t4">{String(i + 1).padStart(2, "0")}</span>
        <span className="font-mono text-[10.5px] text-t4">{node.kinds.map((kk) => LABEL[kk]).join(" + ")}</span>
      </div>
      <div>
        <div className="text-[15.5px] font-medium tracking-[-0.015em] text-t1">{node.name}</div>
        <div className="mt-0.5 flex items-center justify-between font-mono text-[10.5px] text-t3">
          <span>{node.decisions.length > 2 ? `${node.decisions[0][0]}–${node.decisions.at(-1)?.[0]}` : node.decisions.length ? node.decisions.map((d) => d[0]).join(" ") : "—"}</span>
          {ms !== undefined && <span className="hidden xl:inline">{fmt(ms)}</span>}
        </div>
      </div>
    </button>
  );
}

function fmt(ms: number) {
  if (ms < 1000) return `${ms} ms`;
  const s = ms / 1000;
  return s < 60 ? `${s.toFixed(1)} s` : `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
}

/** A boxed label centred on (x, y) in the graph's coordinates; `left` anchors its left edge at x instead. */
function Label({ x, y, left, children }: { x: number; y: number; left?: boolean; children: ReactNode }) {
  return (
    <span
      className="absolute whitespace-nowrap border border-line-2 bg-surface px-2.5 py-1 font-mono text-[11px] leading-none text-t2"
      style={{ left: `${(x / W) * 100}%`, top: `${(y / H) * 100}%`, transform: left ? "translate(0, -50%)" : "translate(-50%, -50%)" }}
    >
      {children}
    </span>
  );
}
