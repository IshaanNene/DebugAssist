import { evalDate, type BugAgg, type Lane, type Results as R, type Row } from "@/lib/data";

const LANES: [string, Lane][] = [
  ["root cause", "rca"],
  ["fix validated", "validated"],
  ["hidden test", "hidden_tests"],
];

// Pass / partly (some seeds) / miss / not applicable. A miss stays visible and labelled — just not alarm-red.
const TONE = {
  pass: "bg-good",
  part: "bg-warn",
  miss: "miss",
  na: "border border-dashed border-line-dash",
};

function cellTone(c: { pass: number; n: number; exact?: number }, lane: Lane): { cls: string; label: string } {
  if (!c.n) return { cls: TONE.na, label: "n/a" };
  const rate = c.pass / c.n;
  const counts = c.n > 1 ? ` (${c.pass}/${c.n} runs)` : "";
  if (rate === 1) {
    const close = lane === "rca" && (c.exact ?? 0) < c.n;
    return { cls: close ? TONE.part : TONE.pass, label: (close ? "right file or module" : "yes") + counts };
  }
  if (rate > 0) return { cls: TONE.part, label: `sometimes${counts}` };
  return { cls: TONE.miss, label: `no${counts}` };
}

function Cell({ c, lane, title, i = 0, r = 0, size = "md" }: { c: BugAgg["lanes"][Lane]; lane: Lane; title: string; i?: number; r?: number; size?: "md" | "sm" }) {
  const t = cellTone(c, lane);
  const showFrac = c.n > 1 && c.pass > 0 && c.pass < c.n;
  return (
    <div
      className={`cell relative grid place-items-center ${size === "md" ? "h-[24px] w-[24px]" : "h-[18px] w-[18px]"} ${t.cls}`}
      style={{ ["--i" as string]: i, ["--r" as string]: r }}
      title={`${title}: ${t.label}`}
    >
      {showFrac && <span className="font-mono text-[8.5px] leading-none text-t1">{c.pass}</span>}
    </div>
  );
}

/** A single run as an aggregate of one, so re-run panels share the grid's cells. */
function one(row: Row | undefined, ours: boolean): BugAgg["lanes"] {
  if (!row) return { rca: { pass: 0, n: 0 }, validated: { pass: 0, n: 0 }, hidden_tests: { pass: 0, n: 0 } };
  const ran = row.hidden_tests === "True" || row.hidden_tests === "False";
  return {
    rca: { pass: row.rca === "exact" || row.rca === "directional" ? 1 : 0, exact: row.rca === "exact" ? 1 : 0, n: 1 },
    validated: ours ? { pass: row.validated === "True" ? 1 : 0, n: 1 } : { pass: 0, n: 0 },
    hidden_tests: { pass: row.hidden_tests === "True" ? 1 : 0, n: ran ? 1 : 0 },
  };
}

export function Results({ data }: { data: R }) {
  const h = data.headline;
  const before = Object.fromEntries(data.baseline.map((r) => [r.bug, r]));
  const near = (rs: Row[]) => rs.filter((r) => r.rca === "exact" || r.rca === "directional").length;
  const passed = (rs: Row[]) => rs.filter((r) => r.hidden_tests === "True").length;
  // Context-engineering arms measure tokens, not fixes; they are compared in the Tokens section.
  const arms = data.arms.filter((a) => !a.name.startsWith("context-"));
  return (
    <div>
      {/* headline numbers */}
      <div className="cbox">
        <div className="grid grid-cols-2 gap-px bg-line sm:grid-cols-3 lg:grid-cols-6">
          {data.stats.map((s, i) => (
            <div key={s.label} className="fx bg-surface p-5" style={{ ["--i" as string]: i }}>
              <div className="font-display text-[38px] font-medium leading-none tracking-[-0.03em] text-t1 tabular-nums">
                <span data-count>{s.value}</span>
              </div>
              <div className="mt-2 text-[12.5px] leading-snug text-t3">{s.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* per-bug grid */}
      <div className="wave cbox no-top -mt-px overflow-x-auto p-5">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <span className="font-mono text-[11px] uppercase tracking-[0.04em] text-t3">
            {h.current ? `Full catalog · ${h.label}` : "Baseline"} · {h.bugs.length} bugs · {data.model} ·{" "}
            {h.seeds > 1 ? `${h.seeds} seeds each` : "one seed"} · {evalDate(h.eval)}
            {h.commit ? ` · ${h.commit}` : ""}
          </span>
          <span className="font-mono text-[11px] text-t3">hover a cell for its value</span>
        </div>
        {!h.current && (
          <p className="mb-4 max-w-[80ch] text-[13px] leading-[1.55] text-t3">
            This is the first full run, on the code of {evalDate(h.eval)} — before the cross-repo hand-off and the
            fix-quality changes. Most of its misses were in the bugs those changes targeted; the re-runs below show the
            same bugs on later code. A full re-run of every bug, several seeds each, is next.
          </p>
        )}
        <table className="border-separate border-spacing-[3px]">
          <thead>
            <tr>
              <th />
              {h.bugs.map((b) => (
                <th
                  key={b.bug}
                  className={`pb-1 font-mono text-[10px] font-normal ${b.ours ? "text-t3" : "text-[#1f8fa8]"}`}
                  title={b.ours ? "needs a code fix" : "not our bug: the right answer is routing"}
                >
                  {b.bug.slice(-3)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {LANES.map(([lab, k], li) => (
              <tr key={k}>
                <td className="whitespace-nowrap pr-3 text-[12.5px] text-t2">{lab}</td>
                {h.bugs.map((b, ci) => (
                  <td key={b.bug}>
                    <Cell c={b.lanes[k]} lane={k} title={`${b.bug} ${lab}`} i={ci} r={li} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1.5 text-[12px] text-t3">
          <Legend cls={TONE.pass} label="yes — exact" />
          <Legend cls={TONE.part} label={h.seeds > 1 ? "right file or module, or some seeds" : "right file or module"} />
          <Legend cls={TONE.miss} label="no" />
          <Legend cls={TONE.na} label="not applicable" />
          <span className="text-[#1f8fa8]">blue ids: not our bug — the right answer is routing</span>
        </div>
      </div>

      {/* re-runs on later code */}
      {arms.map((arm, ai) => {
        const prev = arm.rows.map((r) => before[r.bug]).filter(Boolean);
        return (
          <div key={arm.name} className={`cbox -mt-px no-top ${ai < arms.length - 1 ? "no-bottom" : ""} grid md:grid-cols-[240px_1fr]`}>
            <div className="stripes border-b border-line p-5 md:border-b-0 md:border-r">
              <div className="font-mono text-[11px] uppercase tracking-[0.04em] text-t3">re-run · {arm.commit}</div>
              <div className="mt-1 font-display text-[22px] font-medium tracking-[-0.02em]">{arm.name}</div>
              <dl className="mt-3 space-y-1 text-[12.5px] text-t3">
                <div>
                  root cause right or close{" "}
                  <b className="font-medium text-t1">
                    {near(prev)} → {near(arm.rows)}
                  </b>{" "}
                  of {arm.rows.length}
                </div>
                <div>
                  hidden tests passing{" "}
                  <b className="font-medium text-t1">
                    {passed(prev)} → {passed(arm.rows)}
                  </b>
                </div>
              </dl>
              <div className="mt-3 font-mono text-[10px] text-t4">per bug: left = baseline · right = this re-run</div>
            </div>
            <div className="wave flex flex-wrap gap-x-6 gap-y-4 p-5">
              {arm.rows.map((r, ci) => (
                <div key={r.bug}>
                  <div className="mb-1 text-center font-mono text-[10px] text-t3">{r.bug.slice(-3)}</div>
                  <div className="grid grid-cols-2 gap-[3px]">
                    {LANES.map(([lab, k], li) =>
                      [one(before[r.bug], data.ours[r.bug]), one(r, data.ours[r.bug])].map((lanes, j) => (
                        <Cell key={`${k}${j}`} c={lanes[k]} lane={k} size="sm" title={`${r.bug} ${lab} ${j ? "re-run" : "baseline"}`} i={ci * 2 + j * 4} r={li} />
                      )),
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Legend({ cls, label }: { cls: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`inline-block h-2.5 w-2.5 ${cls}`} />
      {label}
    </span>
  );
}
