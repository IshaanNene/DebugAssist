import type { ReactNode } from "react";

// A small drafting kit for the chapter pages' figures. Shapes follow the usual flowchart and data-flow conventions,
// all straight-edged and closed: a process is a rectangle, a decision a diamond, a data store a rectangle with an
// ID compartment, a document a sheet with a folded corner, an outside party a rectangle with a hard offset shadow,
// and "many of these" a short stack. Swimlanes split a drawing by who may see what. Outlines are SVG; text is HTML
// laid over each shape's usable area, set top-down; labels knock out the lines behind them. Below `xl` (where the
// column is narrower than the drawings were laid out for) the drawing is replaced by its steps as a numbered list.

export type Shape = "process" | "decision" | "store" | "doc" | "external" | "stack";

/** Fill and colour: who does the work (Clef amber, LLM violet), what holds (green), what broke (red), the outcome to
 * look at (highlighter yellow), and the neutral inks. */
export type Tone = "plain" | "ink" | "hatch" | "dashed" | "sunk" | "clef" | "llm" | "good" | "bad" | "mark";

// [fill, stroke, tag colour] for the coloured tones
const COLOURED: Partial<Record<Tone, [string, string, string]>> = {
  clef: ["color-mix(in srgb, var(--actor-clef) 22%, var(--raised))", "var(--actor-clef)", "text-clef"],
  llm: ["color-mix(in srgb, var(--actor-llm) 17%, var(--raised))", "var(--actor-llm)", "text-llm"],
  good: ["color-mix(in srgb, var(--pass) 18%, var(--raised))", "var(--pass)", "text-good"],
  bad: ["color-mix(in srgb, var(--signal) 16%, var(--raised))", "var(--signal)", "text-signal"],
  mark: ["var(--mark)", "var(--line-strong)", "text-t2"],
};

const TONE_NAME: Partial<Record<Tone, string>> = { clef: "Clef", llm: "LLM", good: "holds", bad: "broke", mark: "outcome" };

export interface DBox {
  x: number;
  y: number;
  w: number;
  h: number;
  title?: ReactNode;
  tag?: ReactNode;
  lines?: ReactNode[];
  tone?: Tone;
  shape?: Shape;
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
  /** a framed tag; otherwise plain text that knocks out whatever line runs behind it */
  boxed?: boolean;
}
export interface DLane {
  y: number;
  h: number;
  label: ReactNode;
}

const SHAPE_NAME: Record<Shape, string> = {
  process: "process",
  decision: "decision",
  store: "data store",
  doc: "document",
  external: "outside party",
  stack: "many of these",
};

/** Shape details, scaled to the box so small glyphs keep their proportions. */
function geo(w: number, h: number) {
  return {
    fold: Math.min(16, h * 0.32, w * 0.3),
    shadow: Math.min(6, h * 0.14, w * 0.14),
    stack: Math.min(6, h * 0.12, w * 0.12),
    sid: Math.min(14, w * 0.22),
  };
}

/** The outline of one box, in the drawing's own coordinates. */
function Outline({ b, i }: { b: DBox; i: number }) {
  const { x, y, w, h } = b;
  const g = geo(w, h);
  const tone = b.tone ?? "plain";
  const c = COLOURED[tone];
  const fill = c ? c[0] : tone === "ink" ? "var(--fg)" : tone === "sunk" ? "var(--sunk)" : tone === "hatch" ? `url(#dh-${i})` : "var(--raised)";
  const stroke = c ? c[1] : tone === "ink" ? "var(--fg)" : tone === "sunk" ? "var(--line-2)" : "var(--line-strong)";
  const p = {
    fill,
    stroke,
    strokeWidth: c && tone !== "mark" ? 1.4 : 1,
    vectorEffect: "non-scaling-stroke" as const,
    strokeDasharray: tone === "dashed" ? "5 4" : undefined,
  };
  const line = { ...p, fill: "none" };
  const hatch =
    tone === "hatch" ? (
      <pattern id={`dh-${i}`} patternUnits="userSpaceOnUse" width={7} height={7} patternTransform="rotate(45)">
        <rect width={7} height={7} fill="var(--sunk)" />
        <line x1={0} y1={0} x2={0} y2={7} stroke="var(--line-2)" strokeWidth={1.4} />
      </pattern>
    ) : null;
  switch (b.shape ?? "process") {
    case "decision":
      return (
        <g>
          {hatch}
          <polygon points={`${x + w / 2},${y} ${x + w},${y + h / 2} ${x + w / 2},${y + h} ${x},${y + h / 2}`} {...p} />
        </g>
      );
    case "store":
      // closed, with an ID compartment down the left side
      return (
        <g>
          {hatch}
          <rect x={x} y={y} width={w} height={h} {...p} />
          <line x1={x + g.sid} x2={x + g.sid} y1={y} y2={y + h} {...line} />
        </g>
      );
    case "doc":
      return (
        <g>
          {hatch}
          <path d={`M${x} ${y} H ${x + w - g.fold} L ${x + w} ${y + g.fold} V ${y + h} H ${x} Z`} {...p} />
          <path d={`M${x + w - g.fold} ${y} V ${y + g.fold} H ${x + w}`} {...line} />
        </g>
      );
    case "external":
      return (
        <g>
          {hatch}
          <rect x={x + g.shadow} y={y + g.shadow} width={w - g.shadow} height={h - g.shadow} fill="var(--fg)" />
          <rect x={x} y={y} width={w - g.shadow} height={h - g.shadow} {...p} />
        </g>
      );
    case "stack":
      return (
        <g>
          {hatch}
          <rect x={x + 2 * g.stack} y={y} width={w - 2 * g.stack} height={h - 2 * g.stack} {...p} fill="var(--raised)" />
          <rect x={x + g.stack} y={y + g.stack} width={w - 2 * g.stack} height={h - 2 * g.stack} {...p} fill="var(--raised)" />
          <rect x={x} y={y + 2 * g.stack} width={w - 2 * g.stack} height={h - 2 * g.stack} {...p} />
        </g>
      );
    default:
      return (
        <g>
          {hatch}
          <rect x={x} y={y} width={w} height={h} {...p} />
        </g>
      );
  }
}

/** The part of a shape text may use. */
function inner(b: DBox): { x: number; y: number; w: number; h: number; center: boolean } {
  const { x, y, w, h } = b;
  const g = geo(w, h);
  switch (b.shape ?? "process") {
    case "decision":
      return { x: x + w * 0.2, y: y + h * 0.22, w: w * 0.6, h: h * 0.56, center: true };
    case "store":
      return { x: x + g.sid, y, w: w - g.sid, h, center: false };
    case "doc":
      return { x, y, w: w - g.fold * 0.75, h, center: false };
    case "external":
      return { x, y, w: w - g.shadow, h: h - g.shadow, center: false };
    case "stack":
      return { x, y: y + 2 * g.stack, w: w - 2 * g.stack, h: h - 2 * g.stack, center: false };
    default:
      return { x, y, w, h, center: false };
  }
}

export function Draw({
  w,
  h,
  boxes,
  edges = [],
  labels = [],
  lanes = [],
  steps,
  svg,
  legend = true,
  names,
}: {
  w: number;
  h: number;
  boxes: DBox[];
  edges?: DEdge[];
  labels?: DLabel[];
  /** horizontal swimlanes, full width, each with a header */
  lanes?: DLane[];
  /** what the drawing says, in order, for narrow screens */
  steps: ReactNode[];
  /** extra SVG drawn under the frames (ticks, axes, lifelines) */
  svg?: ReactNode;
  /** show a key of the shapes and colours used */
  legend?: boolean;
  /** rename a colour in the key, e.g. mark: "this record" */
  names?: Partial<Record<Tone, string>>;
}) {
  const pc = (v: number, of: number) => `${(v / of) * 100}%`;
  const used = [...new Set(boxes.map((b) => b.shape ?? "process"))];
  const tones = [...new Set(boxes.map((b) => b.tone ?? "plain"))].filter((t) => TONE_NAME[t]);
  return (
    <>
      <div className="hidden xl:block">
        <div className="relative w-full" style={{ aspectRatio: `${w} / ${h}` }}>
          <svg viewBox={`0 0 ${w} ${h}`} className="absolute inset-0 h-full w-full overflow-visible" aria-hidden>
            <defs>
              <marker id="dk" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
                <path d="M0 0 L8 4 L0 8 z" fill="var(--line-strong)" />
              </marker>
            </defs>
            {lanes.map((l, i) => (
              <rect key={i} x={0} y={l.y} width={w} height={l.h} fill="none" stroke="var(--line-2)" strokeWidth={1} vectorEffect="non-scaling-stroke" />
            ))}
            {svg}
            {edges.map((e, i) => (
              <path
                key={i}
                d={e.d}
                fill="none"
                stroke="var(--line-strong)"
                strokeWidth={1}
                vectorEffect="non-scaling-stroke"
                strokeDasharray={e.dashed ? "4 4" : undefined}
                markerEnd={e.arrow === false ? undefined : "url(#dk)"}
              />
            ))}
            {boxes.map((b, i) => (
              <Outline key={i} b={b} i={i} />
            ))}
          </svg>
          {lanes.map((l, i) => (
            <span
              key={i}
              className="absolute whitespace-nowrap bg-surface px-1.5 font-mono text-[10.5px] uppercase leading-none tracking-[0.08em] text-t3"
              style={{ left: pc(10, w), top: pc(l.y, h), transform: "translate(0,-50%)" }}
            >
              {l.label}
            </span>
          ))}
          {boxes.map((b, i) => {
            const ink = b.tone === "ink";
            const a = inner(b);
            return (
              <div
                key={i}
                className={`absolute flex flex-col gap-2 overflow-hidden ${a.center ? "items-center justify-center text-center" : "justify-start"} ${b.shape === "decision" ? "p-0" : "px-3.5 py-3"}`}
                style={{ left: pc(a.x, w), top: pc(a.y, h), width: pc(a.w, w), height: pc(a.h, h) }}
              >
                {(b.title || b.tag) && (
                  <div className={`flex items-baseline gap-2 ${a.center ? "flex-col items-center gap-0.5" : "justify-between"}`}>
                    <span className={`text-[14px] font-medium leading-[1.25] tracking-[-0.01em] ${ink ? "text-surface" : "text-t1"}`}>{b.title}</span>
                    {b.tag && <span className={`shrink-0 font-mono text-[10.5px] ${ink ? "text-surface/70" : (COLOURED[b.tone ?? "plain"]?.[2] ?? "text-t3")}`}>{b.tag}</span>}
                  </div>
                )}
                {b.lines && (
                  <div className={`font-mono text-[10.5px] leading-[1.55] ${ink ? "text-surface/80" : "text-t3"}`}>
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
              className={`absolute whitespace-nowrap font-mono text-[10.5px] leading-none ${l.boxed === false ? "bg-surface px-1.5 py-0.5 text-t3" : "border border-line-2 bg-surface px-2 py-1 text-t2"}`}
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
        {legend && (used.length > 1 || tones.length > 0) && <ShapeKey shapes={used.length > 1 ? used : []} tones={tones} names={names} />}
      </div>
      <ol className="grid gap-2 xl:hidden">
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

/** A one-line key of the shapes and colours a drawing uses, each drawn small but in proportion. */
export function ShapeKey({
  shapes,
  tones = [],
  names,
}: {
  shapes: Shape[];
  tones?: Tone[];
  names?: Partial<Record<Tone, string>>;
}) {
  return (
    <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-2.5 border-t border-line pt-3.5 font-mono text-[10.5px] text-t3">
      {shapes.map((s) => (
        <span key={s} className="inline-flex items-center gap-2">
          <svg viewBox="0 0 40 24" width={34} height={20} aria-hidden className="overflow-visible">
            <Outline b={{ x: 1, y: 1, w: 38, h: 22, shape: s }} i={-1} />
          </svg>
          {SHAPE_NAME[s]}
        </span>
      ))}
      {shapes.length > 0 && tones.length > 0 && <span className="h-4 w-px bg-line-2" aria-hidden />}
      {tones.map((t) => (
        <span key={t} className="inline-flex items-center gap-2">
          <svg viewBox="0 0 24 24" width={16} height={16} aria-hidden className="overflow-visible">
            <Outline b={{ x: 1, y: 1, w: 22, h: 22, tone: t }} i={-1} />
          </svg>
          {names?.[t] ?? TONE_NAME[t]}
        </span>
      ))}
    </div>
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
