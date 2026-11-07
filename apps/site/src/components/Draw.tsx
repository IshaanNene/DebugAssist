import type { ReactNode } from "react";

// A small drafting kit for the chapter pages' figures: frames placed in a fixed coordinate box, right-angle
// connectors with arrowheads, and boxed labels — the same language as the home page's diagrams. On phones the
// drawing is replaced by its steps as a numbered list.

export interface DBox {
  x: number;
  y: number;
  w: number;
  h: number;
  title?: ReactNode;
  tag?: ReactNode;
  lines?: ReactNode[];
  tone?: "plain" | "ink" | "hatch" | "dashed" | "sunk";
}
export interface DEdge {
  d: string;
  dashed?: boolean;
  arrow?: boolean;
}
export interface DLabel {
  x: number;
  y: number;
  text: ReactNode;
  anchor?: "c" | "l" | "r";
  boxed?: boolean;
}

const TONE: Record<NonNullable<DBox["tone"]>, string> = {
  plain: "border border-line-strong bg-surface",
  ink: "border border-t1 bg-t1 text-surface",
  hatch: "hatch border border-line-strong bg-sunk",
  dashed: "border border-dashed border-line-strong bg-surface",
  sunk: "border border-line bg-sunk",
};

export function Draw({
  w,
  h,
  boxes,
  edges = [],
  labels = [],
  steps,
  svg,
}: {
  w: number;
  h: number;
  boxes: DBox[];
  edges?: DEdge[];
  labels?: DLabel[];
  /** what the drawing says, in order, for narrow screens */
  steps: ReactNode[];
  /** extra SVG drawn under the frames (ticks, axes, lifelines) */
  svg?: ReactNode;
}) {
  const pc = (v: number, of: number) => `${(v / of) * 100}%`;
  return (
    <>
      <div className="relative hidden w-full lg:block" style={{ aspectRatio: `${w} / ${h}` }}>
        <svg viewBox={`0 0 ${w} ${h}`} className="absolute inset-0 h-full w-full overflow-visible" aria-hidden>
          <defs>
            <marker id="dk" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
              <path d="M0 0 L8 4 L0 8 z" fill="var(--line-strong)" />
            </marker>
          </defs>
          {svg}
          {edges.map((e, i) => (
            <path
              key={i}
              d={e.d}
              fill="none"
              stroke="var(--line-strong)"
              strokeWidth={1}
              strokeDasharray={e.dashed ? "4 4" : undefined}
              markerEnd={e.arrow === false ? undefined : "url(#dk)"}
            />
          ))}
        </svg>
        {boxes.map((b, i) => {
          const ink = b.tone === "ink";
          return (
            <div
              key={i}
              className={`absolute flex flex-col justify-between gap-1 overflow-hidden p-3 ${TONE[b.tone ?? "plain"]}`}
              style={{ left: pc(b.x, w), top: pc(b.y, h), width: pc(b.w, w), height: pc(b.h, h) }}
            >
              {(b.title || b.tag) && (
                <div className="flex items-baseline justify-between gap-2">
                  <span className={`text-[14px] font-medium leading-[1.25] tracking-[-0.01em] ${ink ? "text-surface" : "text-t1"}`}>{b.title}</span>
                  {b.tag && <span className={`shrink-0 font-mono text-[10.5px] ${ink ? "text-surface/70" : "text-t3"}`}>{b.tag}</span>}
                </div>
              )}
              {b.lines && (
                <div className={`font-mono text-[10.5px] leading-[1.5] ${ink ? "text-surface/80" : "text-t3"}`}>
                  {b.lines.map((l, j) => (
                    <div key={j}>{l}</div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
        {labels.map((l, i) => (
          <span
            key={i}
            className={`absolute whitespace-nowrap font-mono text-[10.5px] leading-none ${l.boxed === false ? "text-t3" : "border border-line-2 bg-surface px-2 py-1 text-t2"}`}
            style={{
              left: pc(l.x, w),
              top: pc(l.y, h),
              transform: l.anchor === "l" ? "translate(0,-50%)" : l.anchor === "r" ? "translate(-100%,-50%)" : "translate(-50%,-50%)",
            }}
          >
            {l.text}
          </span>
        ))}
      </div>
      <ol className="grid gap-2 lg:hidden">
        {steps.map((s, i) => (
          <li key={i} className="flex gap-3 border border-line bg-surface p-3 text-[14px] leading-[1.5] text-t2">
            <span className="shrink-0 font-mono text-[11px] leading-[21px] text-t4">{String(i + 1).padStart(2, "0")}</span>
            <span>{s}</span>
          </li>
        ))}
      </ol>
    </>
  );
}

/** Horizontal bars: a label, a bar (solid, or hatched for a second series) and the value. */
export function Bars({
  rows,
  max,
  unit = "",
}: {
  rows: { label: ReactNode; value: number; note?: ReactNode; hatch?: boolean }[];
  max?: number;
  unit?: string;
}) {
  const top = max ?? Math.max(...rows.map((r) => r.value), 1);
  return (
    <div className="grid gap-2.5">
      {rows.map((r, i) => (
        <div key={i} className="grid items-center gap-x-4 gap-y-1 sm:grid-cols-[minmax(0,240px)_minmax(0,1fr)_56px]">
          <span className="text-[13.5px] leading-[1.35] text-t2">{r.label}</span>
          <span className="relative h-3 border border-line-strong bg-surface">
            <span className={`absolute inset-y-0 left-0 ${r.hatch ? "hatch-ink" : "bg-t1"}`} style={{ width: `${(r.value / top) * 100}%` }} />
          </span>
          <span className="font-mono text-[12.5px] text-t1 sm:text-right">
            {r.value}
            {unit}
            {r.note && <span className="ml-1 text-t4">{r.note}</span>}
          </span>
        </div>
      ))}
    </div>
  );
}
