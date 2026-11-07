"use client";

import { useState } from "react";
import { Draw, type Shape, type Tone } from "@/components/Draw";

// The system as four layers, bottom (what breaks) to top (what acts), drawn flat as swimlanes. Hovering a layer's
// card explains it under the drawing.

interface Layer {
  name: string;
  blurb: string;
  blocks: [string, string, Tone?, Shape?][];
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
        ["flags", "Unleash", undefined, "store"],
      ],
    },
    {
      name: "Signals",
      blurb:
        "How problems surface: Vitals for crashes and performance, BugDrop for rider reports with screenshots and logs, and OpenTelemetry into Jaeger, Loki and Prometheus.",
      blocks: [
        ["Vitals", "crashes · perf"],
        ["BugDrop", "rider reports"],
        ["traces", "Jaeger", undefined, "store"],
        ["logs", "Loki", undefined, "store"],
        ["metrics", "Prometheus", undefined, "store"],
      ],
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
    },
    {
      name: "Agent core",
      blurb:
        "LangGraph runs the fixed plan; Clef makes each judgement call; LLM agents reason and write code in a network-less sandbox; a policy gate stands before every write.",
      blocks: [
        ["LangGraph", "fixed plan", "ink"],
        ["Clef", "decisions", "clef"],
        ["agents", "LLM · skills", "llm"],
        ["sandbox", "no network", "dashed"],
        ["policy gate", "→ PR · ticket", "mark"],
      ],
    },
  ];
}

// geometry: four lanes stacked top (agent core) to bottom (target system), five columns of blocks each
const LANE = 120;
const GAP = 44;
const BW = 208;
const col = (j: number) => 24 + j * 236;
const laneY = (k: number, n: number) => (n - 1 - k) * (LANE + GAP);
const FLOW = ["crashes · reports · telemetry", "read through MCP, read-only", "evidence, cited by id"];

export function Architecture({ servers, tools }: { servers: number; tools: number }) {
  const L = layers(servers, tools);
  const [hover, setHover] = useState<number | null>(null);
  const n = L.length;
  const H = n * LANE + (n - 1) * GAP;

  return (
    <div>
      <div className="cbox bg-surface">
        <div className="px-6 pb-2 pt-8 sm:px-8">
          <Draw
            w={1200}
            h={H}
            lanes={L.map((l, k) => ({ y: laneY(k, n), h: LANE, label: `${String(k + 1).padStart(2, "0")} · ${l.name}` }))}
            boxes={L.flatMap((l, k) =>
              l.blocks.map(([title, sub, tone, shape], j) => ({
                x: col(j),
                y: laneY(k, n) + 30,
                w: BW,
                h: 70,
                title,
                lines: [sub],
                tone: hover === k && !tone ? "mark" : tone,
                shape,
              })),
            )}
            edges={[0, 1, 2].map((k) => ({ d: `M600 ${laneY(k, n)} V ${laneY(k + 1, n) + LANE}` }))}
            labels={[0, 1, 2].map((k) => ({
              x: 612,
              y: laneY(k, n) - GAP / 2,
              text: FLOW[k],
              anchor: "l" as const,
              boxed: false,
            }))}
            names={{ mark: "where writes leave" }}
            steps={L.map((l) => `${l.name}: ${l.blocks.map(([t, s2]) => `${t} (${s2})`).join(", ")}.`)}
          />
        </div>
        {/* the hovered layer is explained right under the drawing; otherwise the one-line reading */}
        <div className="flex min-h-[58px] items-center gap-3 border-t border-line px-4 py-2.5" aria-live="polite">
          {hover === null ? (
            <div className="flex w-full items-center justify-between font-mono text-[11px] text-t3">
              <span>signals rise from the app · actions leave through the policy gate</span>
              <span className="hidden sm:inline">hover a layer</span>
            </div>
          ) : (
            <>
              <span className="grid h-[24px] w-[24px] shrink-0 place-items-center border border-t1 bg-mark font-mono text-[11px] text-t1">
                {hover + 1}
              </span>
              <p className="text-[13px] leading-[1.5] text-t2">
                <b className="font-medium text-t1">{L[hover].name}.</b> {L[hover].blurb}
              </p>
            </>
          )}
        </div>
      </div>

      <ol className="cbox no-top -mt-px grid gap-px bg-line sm:grid-cols-2 lg:grid-cols-4">
        {L.map((layer, k) => {
          const on = hover === k;
          return (
            <li
              key={layer.name}
              className={`fx relative cursor-default p-5 transition-colors ${on ? "bg-tint" : "bg-surface"}`}
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
