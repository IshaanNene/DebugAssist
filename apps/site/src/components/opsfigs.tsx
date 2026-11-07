// Charts for the Cost and latency and the Limitations pages. Plain SVG in a fixed coordinate box, drawn like the
// figures in figs.tsx: square marks, hairline axes, colour by meaning (violet the LLM, amber Clef, ink rules).
// Below `lg` the column is too narrow for the labels, so each chart shows its numbers as a list instead.
import type { ReactNode } from "react";

const MONO = "var(--font-mono-src), ui-monospace, monospace";
const SANS = "var(--font-sans-src), Helvetica Neue, Arial, sans-serif";
const NS = { vectorEffect: "non-scaling-stroke" as const };
const LLM = "var(--actor-llm)";
const CLEF = "var(--actor-clef)";

const usd = (v: number) => `$${v.toFixed(3)}`;
const pc = (v: number) => `${Math.round(v * 100)}%`;

function Chart({ w, h, label, children, list }: { w: number; h: number; label: string; children: ReactNode; list: ReactNode }) {
  return (
    <>
      <svg viewBox={`0 0 ${w} ${h}`} className="hidden h-auto w-full lg:block" role="img" aria-label={label}>
        {children}
      </svg>
      <div className="lg:hidden">{list}</div>
    </>
  );
}

function Key({ items }: { items: [ReactNode, string][] }) {
  return (
    <div className="mt-6 hidden flex-wrap items-center gap-x-6 gap-y-2 border-t border-line pt-3.5 font-mono text-[10.5px] text-t3 lg:flex">
      {items.map(([glyph, t]) => (
        <span key={t} className="inline-flex items-center gap-2">
          {glyph}
          {t}
        </span>
      ))}
    </div>
  );
}
const Sq = ({ c, hollow }: { c: string; hollow?: boolean }) => (
  <i className="inline-block h-3 w-3 border-[1.5px]" style={{ background: hollow ? "var(--raised)" : c, borderColor: c }} />
);
const Dash = () => <i className="inline-block h-0 w-5 border-t border-dashed border-t1" />;

/** Text with a paper-coloured backing, so it can sit on a line. */
function Tag({ x, y, children, anchor = "start", size = 13 }: { x: number; y: number; children: ReactNode; anchor?: "start" | "end" | "middle"; size?: number }) {
  const w = String(children).length * size * 0.62 + 10;
  const x0 = anchor === "end" ? x - w : anchor === "middle" ? x - w / 2 : x;
  return (
    <g>
      <rect x={x0} y={y - size * 0.9} width={w} height={size * 1.35} fill="var(--bg)" />
      <text x={x0 + 5} y={y} fontFamily={MONO} fontSize={size} fill="var(--fg-2)">
        {children}
      </text>
    </g>
  );
}

/* ───────────── cost of every run, LLM and Clef stacked ───────────── */

export function CostBars({ runs, p50, p90 }: { runs: { bug: string; seed: string; llm: number; clef: number; usd: number }[]; p50: number; p90: number }) {
  const W = 1200;
  const H = 360;
  const L = 80;
  const R = 1180;
  const T = 24;
  const B = 300;
  const max = Math.max(...runs.map((r) => r.usd));
  const top = Math.ceil(max / 0.02) * 0.02;
  const y = (v: number) => B - (v / top) * (B - T);
  const slot = (R - L) / runs.length;
  const bw = Math.max(2, slot * 0.68);
  const ticks = Array.from({ length: Math.round(top / 0.02) + 1 }, (_, k) => k * 0.02);
  return (
    <>
      <Chart
        w={W}
        h={H}
        label={`Cost of each of ${runs.length} runs, cheapest to dearest; median ${usd(p50)}, 90th percentile ${usd(p90)}, most ${usd(max)}.`}
        list={
          <ul className="space-y-1.5 font-mono text-[12.5px] text-t2">
            <li>{runs.length} runs, cheapest to dearest</li>
            <li>median {usd(p50)} · p90 {usd(p90)} · most {usd(max)}</li>
            <li>cheapest {usd(runs[0]?.usd ?? 0)}</li>
          </ul>
        }
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={R} y1={y(t)} y2={y(t)} stroke="var(--line)" {...NS} />
            <text x={L - 10} y={y(t) + 4} textAnchor="end" fontFamily={MONO} fontSize={12} fill="var(--fg-3)">
              ${t.toFixed(2)}
            </text>
          </g>
        ))}
        {runs.map((r, i) => {
          const x = L + i * slot + (slot - bw) / 2;
          return (
            <g key={`${r.bug}-${r.seed}`}>
              <title>{`${r.bug} seed ${r.seed}: ${usd(r.usd)} (agents ${usd(r.llm)}, decisions ${usd(r.clef)})`}</title>
              <rect x={x} y={y(r.llm)} width={bw} height={B - y(r.llm)} fill={LLM} />
              <rect x={x} y={y(r.llm + r.clef)} width={bw} height={y(r.llm) - y(r.llm + r.clef)} fill="var(--fg-3)" />
            </g>
          );
        })}
        <line x1={L} x2={R} y1={B} y2={B} stroke="var(--fg)" {...NS} />
        {[
          [p50, `median ${usd(p50)}`],
          [p90, `p90 ${usd(p90)}`],
        ].map(([v, t]) => (
          <g key={t as string}>
            <line x1={L} x2={R} y1={y(v as number)} y2={y(v as number)} stroke="var(--fg)" strokeDasharray="5 4" {...NS} />
            <Tag x={L + 8} y={y(v as number) - 7}>
              {t as string}
            </Tag>
          </g>
        ))}
        <text x={L} y={B + 30} fontFamily={MONO} fontSize={12} fill="var(--fg-3)">
          cheapest run
        </text>
        <text x={R} y={B + 30} textAnchor="end" fontFamily={MONO} fontSize={12} fill="var(--fg-3)">
          dearest run
        </text>
        <text x={(L + R) / 2} y={B + 30} textAnchor="middle" fontFamily={MONO} fontSize={12} fill="var(--fg-3)">
          {runs.length} runs, sorted by cost →
        </text>
      </Chart>
      <Key
        items={[
          [<Sq key="l" c={LLM} />, "LLM agents"],
          [<Sq key="c" c="var(--fg-3)" />, "decision calls"],
          [<Dash key="d" />, "median and 90th percentile"],
        ]}
      />
    </>
  );
}

/* ───────────── per-decision latency, p50 to p95 ───────────── */

export function LatencyRanges({ rows }: { rows: { decision: string; n: number; p50: number; p95: number; usdPer1k: number }[] }) {
  const W = 1200;
  const RH = 46;
  const T = 30;
  const H = T + rows.length * RH + 40;
  const L = 250;
  const R = 1000;
  const top = Math.ceil(Math.max(...rows.map((r) => r.p95)) / 2) * 2;
  const x = (s: number) => L + (s / top) * (R - L);
  const ticks = Array.from({ length: top / 2 + 1 }, (_, k) => k * 2);
  const name = (d: string) => d.replace(/^D(\d+)_/, "D$1 ").replaceAll("_", " ");
  const yb = T + rows.length * RH;
  return (
    <>
      <Chart
        w={W}
        h={H}
        label="Latency of each labelled live decision, median to 95th percentile, with cost per thousand calls."
        list={
          <ul className="space-y-1.5 font-mono text-[12.5px] text-t2">
            {rows.map((r) => (
              <li key={r.decision}>
                {name(r.decision)}: p50 {r.p50.toFixed(1)} s · p95 {r.p95.toFixed(1)} s · ${r.usdPer1k.toFixed(2)} / 1k
              </li>
            ))}
          </ul>
        }
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={T - 6} y2={yb} stroke="var(--line)" {...NS} />
            <text x={x(t)} y={yb + 24} textAnchor="middle" fontFamily={MONO} fontSize={12} fill="var(--fg-3)">
              {t} s
            </text>
          </g>
        ))}
        <text x={R + 30} y={T - 10} fontFamily={MONO} fontSize={12} fill="var(--fg-3)">
          $ per 1k calls
        </text>
        {rows.map((r, i) => {
          const cy = T + i * RH + RH / 2;
          return (
            <g key={r.decision}>
              <text x={0} y={cy + 5} fontFamily={SANS} fontSize={15} fill="var(--fg)">
                {name(r.decision)}
              </text>
              <text x={L - 14} y={cy + 5} textAnchor="end" fontFamily={MONO} fontSize={11.5} fill="var(--fg-3)">
                n {r.n}
              </text>
              <line x1={x(r.p50)} x2={x(r.p95)} y1={cy} y2={cy} stroke="var(--fg-2)" strokeWidth={3} {...NS} />
              <rect x={x(r.p50) - 6} y={cy - 6} width={12} height={12} fill="var(--fg-2)" stroke="var(--fg)" strokeWidth={1} {...NS} />
              <line x1={x(r.p95)} x2={x(r.p95)} y1={cy - 9} y2={cy + 9} stroke="var(--fg)" strokeWidth={1.4} {...NS} />
              <text x={R + 30} y={cy + 5} fontFamily={MONO} fontSize={13} fill="var(--fg-2)">
                ${r.usdPer1k.toFixed(2)}
              </text>
            </g>
          );
        })}
        <line x1={L} x2={R} y1={yb} y2={yb} stroke="var(--fg)" {...NS} />
      </Chart>
      <Key
        items={[
          [<Sq key="m" c="var(--fg-2)" />, "median (p50)"],
          [<i key="t" className="inline-block h-3 w-0 border-l-[1.5px] border-t1" />, "95th percentile"],
        ]}
      />
    </>
  );
}

/* ───────────── Clef against the LLM decider, end to end ───────────── */

export function Dumbbell({ lanes, clefSeeds }: { lanes: { label: string; clef: number; noClef: number; diff?: [number, number] }[]; clefSeeds: number }) {
  const W = 1200;
  const RH = 58;
  const T = 34;
  const yb = T + lanes.length * RH;
  const H = yb + 40;
  const L = 330;
  const R = 1000;
  const x = (v: number) => L + v * (R - L);
  const pts = (v: number) => `${v >= 0 ? "+" : "−"}${Math.abs(Math.round(v * 100))}`;
  return (
    <>
      <Chart
        w={W}
        h={H}
        label="Pass rates with Clef and with an LLM decider, on the same bugs."
        list={
          <ul className="space-y-1.5 font-mono text-[12.5px] text-t2">
            {lanes.map((l) => (
              <li key={l.label}>
                {l.label}: Clef {pc(l.clef)} · LLM decider {pc(l.noClef)}
                {l.diff ? ` · difference 95% CI ${pts(l.diff[0])} to ${pts(l.diff[1])} pts` : ""}
              </li>
            ))}
          </ul>
        }
      >
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={T - 6} y2={yb} stroke="var(--line)" {...NS} />
            <text x={x(t)} y={yb + 24} textAnchor="middle" fontFamily={MONO} fontSize={12} fill="var(--fg-3)">
              {pc(t)}
            </text>
          </g>
        ))}
        {lanes.some((l) => l.diff) && (
          <text x={W} y={T - 6} textAnchor="end" fontFamily={MONO} fontSize={12} fill="var(--fg-3)">
            difference, 95% CI (pts)
          </text>
        )}
        {lanes.map((l, i) => {
          const cy = T + i * RH + RH / 2;
          const [a, b] = [Math.min(l.clef, l.noClef), Math.max(l.clef, l.noClef)];
          const clefRight = l.clef >= l.noClef;
          return (
            <g key={l.label}>
              <text x={0} y={cy + 5} fontFamily={SANS} fontSize={15} fill="var(--fg)">
                {l.label}
              </text>
              <line x1={x(a)} x2={x(b)} y1={cy} y2={cy} stroke="var(--fg-3)" strokeWidth={2} {...NS} />
              <rect x={x(l.noClef) - 7} y={cy - 7} width={14} height={14} fill={LLM} stroke="var(--fg)" strokeWidth={1} {...NS} />
              <rect x={x(l.clef) - 7} y={cy - 7} width={14} height={14} fill={CLEF} stroke="var(--fg)" strokeWidth={1} {...NS} />
              <text x={x(clefRight ? l.noClef : l.clef) - 14} y={cy + 5} textAnchor="end" fontFamily={MONO} fontSize={12.5} fill="var(--fg-2)">
                {pc(a)}
              </text>
              <text x={x(clefRight ? l.clef : l.noClef) + 14} y={cy + 5} fontFamily={MONO} fontSize={12.5} fill="var(--fg-2)">
                {pc(b)}
              </text>
              {l.diff && (
                <text x={W} y={cy + 5} textAnchor="end" fontFamily={MONO} fontSize={12.5} fill="var(--fg-3)">
                  {pts(l.diff[0])} to {pts(l.diff[1])}
                </text>
              )}
            </g>
          );
        })}
        <line x1={L} x2={R} y1={yb} y2={yb} stroke="var(--fg)" {...NS} />
      </Chart>
      <Key
        items={[
          [<Sq key="c" c={CLEF} />, `Clef · ${clefSeeds} seeds per bug`],
          [<Sq key="l" c={LLM} />, "LLM decider · 1 seed per bug"],
        ]}
      />
    </>
  );
}

/* ───────────── each decision re-decided by Clef, an LLM and rules ───────────── */

type Acc = Record<"clef" | "clef-flash" | "llm" | "rules", number | null>;

export function ReplayDots({ rows }: { rows: { decision: string; n: number; acc: Acc }[] }) {
  const W = 1200;
  const RH = 52;
  const T = 20;
  const yb = T + rows.length * RH;
  const H = yb + 40;
  const L = 280;
  const R = 1040;
  const x = (v: number) => L + v * (R - L);
  const name = (d: string) => d.replace(/^D(\d+)_/, "D$1 ").replaceAll("_", " ");
  const best = (a: Acc) => {
    const e = (Object.entries(a) as [keyof Acc, number | null][]).filter((p): p is [keyof Acc, number] => p[1] !== null);
    const m = Math.max(...e.map((p) => p[1]));
    return e.filter((p) => p[1] === m).map((p) => p[0]);
  };
  const glyph = (k: keyof Acc, v: number, cy: number) => {
    const cx = x(v);
    if (k === "rules")
      return <polygon key={k} points={`${cx},${cy - 9} ${cx + 9},${cy} ${cx},${cy + 9} ${cx - 9},${cy}`} fill="var(--fg)" />;
    const c = k === "llm" ? LLM : CLEF;
    return <rect key={k} x={cx - 6.5} y={cy - 6.5} width={13} height={13} fill={k === "clef-flash" ? "var(--raised)" : c} stroke={c} strokeWidth={2} {...NS} />;
  };
  return (
    <>
      <Chart
        w={W}
        h={H}
        label="Accuracy of each logged decision when re-decided by Clef, Clef-flash, an LLM and hand-written rules."
        list={
          <ul className="space-y-1.5 font-mono text-[12.5px] text-t2">
            {rows.map((r) => (
              <li key={r.decision}>
                {name(r.decision)} (n {r.n}): Clef {pc(r.acc.clef ?? 0)} · LLM {pc(r.acc.llm ?? 0)}
                {r.acc.rules !== null ? ` · rules ${pc(r.acc.rules)}` : " · no rule"}
              </li>
            ))}
          </ul>
        }
      >
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={T - 6} y2={yb} stroke="var(--line)" {...NS} />
            <text x={x(t)} y={yb + 24} textAnchor="middle" fontFamily={MONO} fontSize={12} fill="var(--fg-3)">
              {pc(t)}
            </text>
          </g>
        ))}
        <text x={R + 40} y={T - 4} fontFamily={MONO} fontSize={12} fill="var(--fg-3)">
          best
        </text>
        {rows.map((r, i) => {
          const cy = T + i * RH + RH / 2;
          const order: (keyof Acc)[] = ["rules", "llm", "clef-flash", "clef"];
          const b = best(r.acc);
          return (
            <g key={r.decision}>
              <text x={0} y={cy + 5} fontFamily={SANS} fontSize={15} fill="var(--fg)">
                {name(r.decision)}
              </text>
              <text x={L - 14} y={cy + 5} textAnchor="end" fontFamily={MONO} fontSize={11.5} fill="var(--fg-3)">
                n {r.n}
              </text>
              <line x1={L} x2={R} y1={cy} y2={cy} stroke="var(--line)" strokeDasharray="2 4" {...NS} />
              {order.map((k) => (r.acc[k] === null ? null : glyph(k, r.acc[k] as number, cy)))}
              <text x={R + 40} y={cy + 5} fontFamily={MONO} fontSize={12.5} fill={b.includes("rules") ? "var(--signal)" : "var(--fg-2)"}>
                {b.length === 3 || b.length === 4 ? "tie" : b.join(" · ")}
              </text>
            </g>
          );
        })}
        <line x1={L} x2={R} y1={yb} y2={yb} stroke="var(--fg)" {...NS} />
      </Chart>
      <Key
        items={[
          [<Sq key="c" c={CLEF} />, "Clef"],
          [<Sq key="f" c={CLEF} hollow />, "Clef-flash"],
          [<Sq key="l" c={LLM} />, "LLM"],
          [<i key="r" className="inline-block h-2.5 w-2.5 rotate-45 bg-t1" />, "hand-written rules"],
        ]}
      />
    </>
  );
}
