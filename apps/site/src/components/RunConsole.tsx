"use client";

import { useEffect, useEffectEvent, useRef, useState, type ReactNode } from "react";
import { Receipt, type Source } from "@/components/Receipt";
import type { FeaturedRun, RunTimings } from "@/lib/data";

// The hero: one real evaluated run replayed on its true time axis (step timings from run-timings.json). Bars are
// coloured by who acted; a diamond marks a step that took a Clef decision. Server-rendered in its finished state;
// the replay starts once when the console scrolls into view, never with reduced motion.

type Actor = "code" | "llm" | "clef";
const actorOf = (kind: string): Actor => (kind.startsWith("llm") ? "llm" : kind === "clef" ? "clef" : "code");
const COLOR: Record<Actor, string> = { code: "var(--actor-code)", llm: "var(--actor-llm)", clef: "var(--actor-clef)" };
const ACTOR: Record<Actor, string> = { code: "code", llm: "LLM agent", clef: "Clef" };

const STEP: Record<string, { label: string; phase: string }> = {
  ingest: { label: "Ingest", phase: "Detect" },
  auto_triage: { label: "Triage", phase: "Detect" },
  context_collector: { label: "Gather evidence", phase: "Investigate" },
  classify_rca: { label: "Root cause", phase: "Investigate" },
  mitigate: { label: "Mitigate", phase: "Investigate" },
  fix: { label: "Reproduce & fix", phase: "Fix" },
  validate: { label: "Validate", phase: "Fix" },
  ship_gate: { label: "Ship gate", phase: "Ship" },
  pr_and_notify: { label: "Pull request", phase: "Ship" },
  post_merge_watch: { label: "Watch", phase: "Ship" },
};

const SPEEDS = [10, 30, 60];
const pad = (t: number) => t.toFixed(1).padStart(5, "0");

export function RunConsole({
  run,
  timings,
  report,
  model,
  notes,
}: {
  run: FeaturedRun;
  timings: RunTimings;
  report: string;
  model: string;
  /** what each step produced, by node, shown as the step finishes */
  notes: Record<string, ReactNode>;
}) {
  const wall = run.wallS;
  const steps = timings.steps.map((s) => ({
    ...s,
    s: s.startMs / 1000,
    e: (s.startMs + s.ms) / 1000,
    actor: actorOf(s.kind),
    clef: s.kind.includes("clef"),
    ...(STEP[s.node] ?? { label: s.node, phase: "" }),
  }));
  // contiguous phases, for the bands over the tracks
  const phases: { name: string; s: number; e: number }[] = [];
  for (const st of steps) {
    const last = phases[phases.length - 1];
    if (last && last.name === st.phase) last.e = st.e;
    else phases.push({ name: st.phase, s: st.s, e: st.e });
  }
  const at = (x: number) => `${((x / wall) * 100).toFixed(3)}%`;

  const [t, setT] = useState(wall); // finished, as rendered on the server
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(30);
  const raf = useRef(0);
  const clock = useRef({ t0: -1, last: 0, speed: 30 }); // t0 and last are rAF timestamps
  const root = useRef<HTMLDivElement>(null);

  const stop = () => {
    cancelAnimationFrame(raf.current);
    setPlaying(false);
  };
  const play = () => {
    cancelAnimationFrame(raf.current);
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const ends = steps.map((s) => s.e);
    clock.current.t0 = -1; // set by the first frame
    setPlaying(true);
    const tick = (now: number) => {
      if (clock.current.t0 < 0) clock.current.t0 = now;
      clock.current.last = now;
      let x = ((now - clock.current.t0) / 1000) * clock.current.speed;
      if (x >= wall) {
        setT(wall);
        setPlaying(false);
        return;
      }
      if (still) x = ends.filter((e) => e <= x).pop() ?? 0; // step to step, no sweep
      setT(x);
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
  };
  const onVisible = useEffectEvent(() => play());

  // replay once, the first time the console is mostly in view
  useEffect(() => {
    const el = root.current;
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const io = new IntersectionObserver(
      ([e]) => {
        if (!e.isIntersecting) return;
        io.disconnect();
        onVisible();
      },
      { threshold: 0.45 },
    );
    io.observe(el);
    return () => {
      io.disconnect();
      cancelAnimationFrame(raf.current);
    };
  }, []);

  const changeSpeed = (s: number) => {
    // keep the replay where it is: rebase the start so elapsed × speed stays the same
    const { t0, last, speed: v } = clock.current;
    if (t0 >= 0) {
      const x = ((last - t0) / 1000) * v;
      clock.current.t0 = last - (x / s) * 1000;
    }
    clock.current.speed = s;
    setSpeed(s);
  };

  const csv = `evals/reports/${report}/results.csv`;
  const row = `run_id ${run.runId}`;
  const stepFile = `evals/reports/${report}/run-timings.json`;
  const done = t >= wall;
  const totals: [string, string, Source][] = [
    ["Wall time", `${run.wallS.toFixed(1)} s`, { file: csv, row, field: "wall_s", raw: run.wallS, note: `Its ${steps.length} steps add up to ${(timings.stepsMs / 1000).toFixed(1)} s; the rest is time between steps.` }],
    ["Agent turns", String(run.turns), { file: csv, row, field: "turns", raw: run.turns }],
    ["Clef decisions", String(run.decisions), { file: csv, row, field: "labelled_decisions", raw: run.decisions }],
    ["Cost", `$${run.usd.toFixed(4)}`, { file: csv, row, field: "usd", raw: run.usd, note: `LLM $${run.llmUsd} plus Clef $${run.clefUsd}, on ${model}.` }],
  ];

  return (
    <div ref={root} className="console overflow-hidden rounded-[12px] border border-line-2">
      {/* header: the incident, the clock, the controls */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-line px-5 py-4 md:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <span className="signal-dot" aria-hidden />
          <div className="min-w-0">
            <div className="font-mono text-[12.5px] font-medium text-t1">
              {run.issue} · {run.agentType}
            </div>
            <div className="font-mono text-[11px] text-t3">
              {run.bug} · {model} · run {run.runId}
            </div>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-5">
          <div className="text-right">
            <div className="label text-[10px] text-t3">{done ? "Run finished" : playing ? "Replaying" : "Paused"}</div>
            <div className="font-mono text-[26px] font-medium leading-none tracking-[-0.02em] text-amber tabular-nums" aria-hidden>
              T+{pad(t)}
              <span className="text-[14px] text-t3"> s</span>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => (playing ? stop() : play())}
              className="inline-flex h-9 items-center gap-2 rounded-[6px] bg-amber-fill px-3.5 text-[13px] font-semibold text-ink transition-transform active:translate-y-px"
            >
              <span aria-hidden className="font-mono text-[11px]">{playing ? "■" : "▶"}</span>
              {playing ? "Stop" : done ? "Replay" : "Play"}
            </button>
            <div role="group" aria-label="Replay speed" className="hidden rounded-[6px] border border-line p-0.5 sm:flex">
              {SPEEDS.map((s) => (
                <button
                  key={s}
                  type="button"
                  aria-pressed={speed === s}
                  onClick={() => changeSpeed(s)}
                  className={`rounded-[4px] px-2 py-1 font-mono text-[11px] tabular-nums transition-colors ${
                    speed === s ? "bg-sunk text-t1 shadow-[inset_0_0_0_1px_var(--line-2)]" : "text-t3 hover:text-t1"
                  }`}
                >
                  {s}×
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="grid xl:grid-cols-[minmax(0,1fr)_340px]">
        {/* the waterfall */}
        <div className="min-w-0 px-5 pb-5 pt-5 md:px-6">
          <div className="console-grid">
            {/* the clock's hand, over the track column */}
            <div className="now-rail" aria-hidden>
              <i className="now" style={{ left: at(t), opacity: done ? 0 : 1 }} />
            </div>
            {/* phase bands */}
            <div className="hidden md:block" />
            <div className="relative col-span-full h-9 md:col-span-1">
              {phases.map((p, i) => (
                <div
                  key={p.name}
                  className={`phase absolute bottom-0 ${i % 2 ? "h-[18px]" : "h-full"}`}
                  data-on={t >= p.s ? "" : undefined}
                  style={{ left: at(p.s), width: at(p.e - p.s) }}
                >
                  <span className="label text-[10px]">{p.name}</span>
                </div>
              ))}
            </div>
            <div className="hidden md:block" />

            {steps.map((st) => {
              const p = Math.max(0, Math.min(1, (t - st.s) / Math.max(st.e - st.s, 0.001)));
              const state = t < st.s ? "wait" : t < st.e ? "run" : "done";
              return (
                <div key={`${st.node}-${st.s}`} className="contents" data-state={state}>
                  <div className="flex min-w-0 items-baseline gap-2 md:block">
                    <div className="text-[14px] font-semibold tracking-[-0.01em] text-t1">{st.label}</div>
                    <div className="font-mono text-[10.5px] text-t3">
                      {st.node} · {ACTOR[st.actor]}
                      {st.clef && st.actor !== "clef" ? " + Clef" : ""}
                    </div>
                  </div>
                  <div className="track">
                    <i
                      className={`bar ${state === "run" ? "bar-run" : ""}`}
                      style={{
                        left: at(st.s),
                        width: `max(${at(st.e - st.s)}, 4px)`,
                        transform: `scaleX(${p})`,
                        background: COLOR[st.actor],
                      }}
                    />
                    {st.clef && <i className="diamond" style={{ left: `calc(${at(st.s)} - 4px)` }} data-on={t >= st.s ? "" : undefined} />}
                  </div>
                  <div className="text-right font-mono text-[11.5px] text-t2">
                    <Receipt source={{ file: stepFile, row: `run_id ${run.runId} · step ${st.node}`, field: "ms", raw: st.ms }}>
                      {(st.ms / 1000).toFixed(1)} s
                    </Receipt>
                  </div>
                </div>
              );
            })}

            {/* axis */}
            <div className="hidden md:block" />
            <div className="relative col-span-full h-6 font-mono text-[10px] text-t3 tabular-nums md:col-span-1">
              {[0, 50, 100, 150, 200].filter((x) => x < wall).map((x) => (
                <span key={x} className="absolute top-1.5 -translate-x-1/2 whitespace-nowrap first:translate-x-0" style={{ left: at(x) }}>
                  {x} s
                </span>
              ))}
            </div>
            <div className="hidden md:block" />
          </div>
          <div className="mt-2 flex flex-wrap gap-x-5 gap-y-2 font-mono text-[10.5px] text-t3">
            <span className="inline-flex items-center gap-2"><i className="h-[6px] w-4 rounded-[1px] bg-code" />deterministic code</span>
            <span className="inline-flex items-center gap-2"><i className="h-[6px] w-4 rounded-[1px] bg-llm" />LLM agent</span>
            <span className="inline-flex items-center gap-2"><i className="diamond-key" />Clef decision</span>
          </div>
        </div>

        {/* what each step produced */}
        <div className="border-t border-line bg-sunk/50 px-5 py-5 md:px-6 xl:border-l xl:border-t-0">
          <div className="label text-[10px] text-t3">Findings</div>
          <ol className="mt-3 space-y-3">
            {steps
              .filter((st) => notes[st.node])
              .map((st) => {
                const on = t >= st.e;
                return (
                  <li key={st.node} className={`finding grid grid-cols-[54px_minmax(0,1fr)] gap-2 ${on ? "" : "finding-off"}`}>
                    <span className="pt-[2px] font-mono text-[10.5px] text-t3 tabular-nums">T+{st.e.toFixed(1)}</span>
                    <span className="flex gap-2 text-[13.5px] leading-[1.45] text-t2">
                      <i className="mt-[6px] h-[7px] w-[7px] shrink-0 rounded-full" style={{ background: COLOR[st.actor] }} />
                      <span className="min-w-0">{notes[st.node]}</span>
                    </span>
                  </li>
                );
              })}
          </ol>
          <p className="caveat mt-5 text-[14px] text-t3">
            An evaluation run: it stops after validation, so no pull request was opened.
          </p>
        </div>
      </div>

      {/* totals */}
      <div className="grid grid-cols-2 gap-px border-t border-line bg-line md:grid-cols-4">
        {totals.map(([k, v, source]) => (
          <div key={k} className="bg-raised px-5 py-4 md:px-6">
            <div className="label text-[10px] text-t3">{k}</div>
            <div className={`mt-1.5 font-mono text-[22px] font-medium tracking-[-0.02em] text-t1 transition-opacity duration-500 ${done ? "" : "opacity-35"}`}>
              <Receipt source={source}>{v}</Receipt>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
