"use client";

import { Background, Controls, MarkerType, Position, ReactFlow, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { GraphNode } from "@/lib/types";

// The fixed plan, laid out as the README draws it. Colours: deterministic gray, LLM blue, Clef amber.
const POS: Record<string, [number, number]> = {
  ingest: [0, 0],
  auto_triage: [190, 0],
  context_collector: [380, 0],
  classify_rca: [570, 0],
  mitigate: [570, 130],
  fix: [380, 130],
  validate: [190, 130],
  ship_gate: [0, 130],
  pr_and_notify: [0, 260],
  post_merge_watch: [190, 260],
};
const EDGES: [string, string, string?][] = [
  ["ingest", "auto_triage"],
  ["auto_triage", "context_collector"],
  ["context_collector", "classify_rca"],
  ["classify_rca", "mitigate", "actionable"],
  ["classify_rca", "ship_gate", "not actionable"],
  ["mitigate", "fix"],
  ["fix", "validate"],
  ["validate", "fix", "retry (D15)"],
  ["validate", "ship_gate"],
  ["ship_gate", "pr_and_notify"],
  ["pr_and_notify", "post_merge_watch"],
];

// Which side edges leave and enter: the first row flows right, the second back left, the third right.
const HANDLES: Record<string, [Position, Position]> = {
  ingest: [Position.Left, Position.Right],
  auto_triage: [Position.Left, Position.Right],
  context_collector: [Position.Left, Position.Right],
  classify_rca: [Position.Left, Position.Bottom],
  mitigate: [Position.Top, Position.Left],
  fix: [Position.Right, Position.Left],
  validate: [Position.Right, Position.Left],
  ship_gate: [Position.Right, Position.Bottom],
  pr_and_notify: [Position.Top, Position.Right],
  post_merge_watch: [Position.Left, Position.Right],
};

function color(kind: string): string {
  if (kind.startsWith("llm")) return "var(--llm)";
  if (kind === "clef") return "var(--clef)";
  return "var(--det)";
}

export interface Lane {
  id: string;
  status: string;
}

export function PipelineGraph({ nodes, lanes = [] }: { nodes: GraphNode[]; lanes?: Lane[] }) {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const flowNodes: Node[] = nodes.map((n) => {
    const [x, y] = POS[n.id] ?? [0, 0];
    const c = color(n.kind);
    const clef = n.kind.includes("clef");
    return {
      id: n.id,
      position: { x, y },
      data: {
        label: (
          <div className="text-left">
            <div className="font-mono text-[11px] font-semibold">{n.id}</div>
            <div className="text-[10px] opacity-70">
              {n.status}
              {n.ms != null && ` · ${(n.ms / 1000).toFixed(1)}s`}
              {n.runs > 1 && ` · ×${n.runs}`}
            </div>
          </div>
        ),
      },
      draggable: false,
      targetPosition: HANDLES[n.id]?.[0],
      sourcePosition: HANDLES[n.id]?.[1],
      style: {
        width: 160,
        borderRadius: 8,
        border: `2px solid ${n.status === "failed" ? "#ef4444" : c}`,
        boxShadow: clef ? "0 0 0 3px color-mix(in srgb, var(--clef) 35%, transparent)" : undefined,
        background: n.status === "done" ? `color-mix(in srgb, ${c} 18%, var(--panel))` : "var(--panel)",
        color: "var(--ink)",
        opacity: n.status === "skipped" || n.status === "pending" ? 0.45 : 1,
        animation: n.status === "running" ? "pulse 1.2s ease-in-out infinite" : undefined,
      },
    };
  });
  lanes.forEach((l, i) => {
    flowNodes.push({
      id: `sub-${l.id}`,
      position: { x: 760, y: -20 + i * 46 },
      data: { label: <div className="font-mono text-[10px]">{l.id} · {l.status}</div> },
      targetPosition: Position.Left,
      draggable: false,
      style: { width: 190, padding: 4, borderRadius: 6, border: "1px dashed var(--llm)", background: "var(--panel)", color: "var(--ink)" },
    });
  });
  const flowEdges: Edge[] = EDGES.filter(([a, b]) => byId.has(a) && byId.has(b)).map(([a, b, label]) => {
    const taken = byId.get(a)?.status === "done" && byId.get(b)?.status === "done";
    return {
      id: `${a}-${b}`,
      source: a,
      target: b,
      label,
      animated: byId.get(b)?.status === "running",
      markerEnd: { type: MarkerType.ArrowClosed },
      style: { stroke: taken ? "var(--ink)" : "var(--line)", strokeWidth: taken ? 1.6 : 1 },
      labelStyle: { fontSize: 10, fill: "var(--muted)" },
    };
  });
  for (const l of lanes) {
    flowEdges.push({ id: `rca-${l.id}`, source: "classify_rca", sourceHandle: null, target: `sub-${l.id}`, style: { stroke: "var(--llm)", strokeDasharray: "4 3" } });
  }
  return (
    <div className="h-[380px] rounded-lg border border-line bg-panel">
      <ReactFlow nodes={flowNodes} edges={flowEdges} fitView proOptions={{ hideAttribution: true }} nodesConnectable={false}>
        <Background gap={20} />
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>
    </div>
  );
}
