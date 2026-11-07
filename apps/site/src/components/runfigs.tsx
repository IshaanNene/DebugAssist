// The featured run as a swimlane sequence: each pipeline step in order, in the lane of whoever did the work, each
// labelled decision under the step that took it (as the ledger recorded it, with Clef's answer from the replay), and
// the steps again on their true clock underneath. Every value comes from the run's records.
import { Draw, type DBox, type DEdge, type DLabel, type Tone } from "@/components/Draw";
import type { RunTimings } from "@/lib/data";
import type { RunDecision } from "@/lib/ops";

const STEP: Record<string, string> = {
  ingest: "Ingest",
  auto_triage: "Triage",
  context_collector: "Context",
  classify_rca: "Root cause",
  mitigate: "Mitigate",
  fix: "Fix",
  validate: "Validate",
};
const s1 = (ms: number) => (ms < 100 ? `${(ms / 1000).toFixed(2)} s` : `${(ms / 1000).toFixed(1)} s`);
const short = (d: string) => d.replace(/^D(\d+)_/, "D$1 ").replaceAll("_", " ");
const BACKEND: Record<string, string> = { llm: "LLM decider", workers_ai: "Clef", mock: "mock", rules: "rules", local: "local Clef" };

export function RunSequence({ timings, decisions, notes }: { timings: RunTimings; decisions: RunDecision[]; notes: Record<string, string[]> }) {
  const W = 1200;
  const n = timings.steps.length;
  const pitch = W / n;
  const bw = pitch - 18;
  const cx = (i: number) => i * pitch + 9;
  const CODE = { y: 0, h: 140 };
  const DEC = { y: 160, h: 186 };
  const LLM = { y: 366, h: 140 };
  const CLOCK = { y: 526, h: 70 };
  const H = CLOCK.y + CLOCK.h;
  const isLlm = (kind: string) => kind.startsWith("llm");
  const laneOf = (kind: string) => (isLlm(kind) ? LLM : CODE);
  const by = (k: string) => laneOf(k).y + 34;
  const bh = 92;

  const boxes: DBox[] = timings.steps.map((s, i) => ({
    x: cx(i),
    y: by(s.kind),
    w: bw,
    h: bh,
    title: STEP[s.node] ?? s.node,
    lines: [s1(s.ms), ...(notes[s.node] ?? [])],
    tone: (isLlm(s.kind) ? "llm" : "plain") as Tone,
  }));

  const edges: DEdge[] = [];
  timings.steps.forEach((s, i) => {
    if (i === n - 1) return;
    const t = timings.steps[i + 1];
    const y0 = by(s.kind) + bh / 2;
    const y1 = by(t.kind) + bh / 2;
    const x0 = cx(i) + bw;
    const x1 = cx(i + 1);
    edges.push({ d: y0 === y1 ? `M${x0} ${y0} H ${x1}` : `M${x0} ${y0} H ${x0 + 9} V ${y1} H ${x1}` });
  });

  const dec: DBox[] = [];
  decisions.forEach((d) => {
    const i = timings.steps.findIndex((s) => s.node === d.stage);
    if (i < 0) return;
    const s = timings.steps[i];
    const x = cx(i);
    dec.push({
      x,
      y: DEC.y + 24,
      w: bw,
      h: 146,
      title: d.decision.replace(/_.*/, ""),
      tag: d.served.correct ? "right" : "wrong",
      tone: d.served.correct ? "plain" : "bad",
      lines: [
        d.decision.replace(/^D\d+_/, "").replaceAll("_", " "),
        `${BACKEND[d.served.backend] ?? d.served.backend}`,
        `p ${d.served.confidence.toFixed(2)} · ${d.served.latencyS.toFixed(1)} s`,
        ...(d.clef ? [`Clef: ${d.clef.band} ${d.clef.correct ? "✓" : "✗"} ${d.clef.confidence.toFixed(2)}`] : []),
      ],
    });
    // the step that took the decision, to the decision: dashed, no arrowhead
    const fromLlm = isLlm(s.kind);
    edges.push({
      d: fromLlm ? `M${x + bw / 2} ${LLM.y + 34} V ${DEC.y + 24 + 146}` : `M${x + bw / 2} ${CODE.y + 34 + bh} V ${DEC.y + 24}`,
      dashed: true,
      arrow: false,
    });
  });

  // the true clock: each step as a segment of the run's summed step time
  const total = timings.stepsMs || 1;
  const tx = (ms: number) => (ms / total) * W;
  const cy = CLOCK.y + 36;
  const clock = (
    <g>
      <line x1={0} x2={W} y1={cy + 7} y2={cy + 7} stroke="var(--line-2)" vectorEffect="non-scaling-stroke" />
      {timings.steps.map((s) => (
        <rect
          key={s.node}
          x={tx(s.startMs)}
          y={cy}
          width={Math.max(1.5, tx(s.ms))}
          height={14}
          fill={isLlm(s.kind) ? "var(--actor-llm)" : "var(--fg)"}
          stroke="var(--bg)"
          strokeWidth={1}
          vectorEffect="non-scaling-stroke"
        />
      ))}
    </g>
  );
  const big = timings.steps.filter((s) => s.ms / total > 0.12);
  const labels: DLabel[] = [
    { x: 0, y: cy + 28, text: "0 s", anchor: "l", boxed: false },
    { x: W, y: cy + 28, text: s1(total), anchor: "r", boxed: false },
    ...big.map((s) => ({ x: tx(s.startMs + s.ms / 2), y: cy - 12, text: `${STEP[s.node] ?? s.node} · ${s1(s.ms)}`, boxed: false })),
  ];

  return (
    <Draw
      w={W}
      h={H}
      lanes={[
        { y: CODE.y, h: CODE.h, label: "pipeline code · host and sandbox" },
        { y: DEC.y, h: DEC.h, label: "decisions · as the ledger recorded them" },
        { y: LLM.y, h: LLM.h, label: "LLM agents · in the sandbox" },
        { y: CLOCK.y, h: CLOCK.h, label: "the same steps on the true clock" },
      ]}
      boxes={[...boxes, ...dec]}
      edges={edges}
      labels={labels}
      svg={clock}
      names={{ bad: "wrong decision" }}
      steps={[
        ...timings.steps.map((s) => {
          const ds = decisions.filter((d) => d.stage === s.node);
          return `${STEP[s.node] ?? s.node} (${isLlm(s.kind) ? "LLM agent" : "code"}, ${s1(s.ms)})${
            ds.length
              ? ` — ${ds
                  .map(
                    (d) =>
                      `${short(d.decision)}: ${BACKEND[d.served.backend] ?? d.served.backend} p ${d.served.confidence.toFixed(2)}, ${d.served.correct ? "right" : "wrong"}${
                        d.clef ? `; Clef in the replay ${d.clef.band}, ${d.clef.correct ? "right" : "wrong"}` : ""
                      }`,
                  )
                  .join("; ")}`
              : ""
          }.`;
        }),
      ]}
    />
  );
}
