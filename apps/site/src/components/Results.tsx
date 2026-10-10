import type { Results as R, Row } from "@/lib/data";

const LANES: [string, string][] = [
  ["root cause", "rca"],
  ["fix validated", "validated"],
  ["hidden test", "hidden_tests"],
];

function tone(row: Row | undefined, key: string, ours: boolean): { cls: string; label: string } {
  const v = row?.[key] ?? "";
  if (!row || (key === "validated" && !ours)) return { cls: "border border-dashed border-line-dash", label: "n/a" };
  if (v === "exact" || v === "True") return { cls: "bg-good", label: v === "True" ? "yes" : "exact" };
  if (v === "directional") return { cls: "bg-warn", label: "directional" };
  if (v === "wrong" || v === "False") return { cls: "bg-bad", label: v === "False" ? "no" : "wrong" };
  return { cls: "border border-dashed border-line-dash", label: "n/a" };
}

function Cell({ row, k, ours, size = "md", title, i = 0, r = 0 }: { row?: Row; k: string; ours: boolean; size?: "md" | "sm"; title: string; i?: number; r?: number }) {
  const t = tone(row, k, ours);
  return (
    <div
      className={`cell ${size === "md" ? "h-[24px] w-[24px]" : "h-[18px] w-[18px]"} ${t.cls} transition-[filter] hover:brightness-110`}
      style={{ ["--i" as string]: i, ["--r" as string]: r }}
      title={`${title}: ${t.label}`}
    />
  );
}

export function Results({ data }: { data: R }) {
  const before = Object.fromEntries(data.baseline.map((r) => [r.bug, r]));
  const near = (rs: Row[]) => rs.filter((r) => r.rca === "exact" || r.rca === "directional").length;
  const passed = (rs: Row[]) => rs.filter((r) => r.hidden_tests === "True").length;
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
            Baseline · {data.baseline.length} bugs · {data.model} · one seed
          </span>
          <span className="font-mono text-[11px] text-t3">hover a cell for its value</span>
        </div>
        <table className="border-separate border-spacing-[3px]">
          <thead>
            <tr>
              <th />
              {data.baseline.map((r) => (
                <th
                  key={r.bug}
                  className={`pb-1 font-mono text-[10px] font-normal ${data.ours[r.bug] ? "text-t3" : "text-[#1f8fa8]"}`}
                  title={data.ours[r.bug] ? "needs a code fix" : "not our bug: the right answer is routing"}
                >
                  {r.bug.slice(-3)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {LANES.map(([lab, k], li) => (
              <tr key={k}>
                <td className="whitespace-nowrap pr-3 text-[12.5px] text-t2">{lab}</td>
                {data.baseline.map((r, ci) => (
                  <td key={r.bug}>
                    <Cell row={r} k={k} ours={data.ours[r.bug]} title={`${r.bug} ${lab}`} i={ci} r={li} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1.5 text-[12px] text-t3">
          <Legend cls="bg-good" label="exact / yes" />
          <Legend cls="bg-warn" label="directional — right file or module" />
          <Legend cls="bg-bad" label="wrong / no" />
          <Legend cls="border border-dashed border-line-dash" label="not applicable" />
          <span className="text-[#1f8fa8]">blue ids: not our bug — the right answer is routing</span>
        </div>
      </div>

      {/* re-runs on later code */}
      {data.arms.map((arm, ai) => {
        const prev = arm.rows.map((r) => before[r.bug]).filter(Boolean);
        return (
          <div key={arm.name} className={`cbox -mt-px no-top ${ai < data.arms.length - 1 ? "no-bottom" : ""} grid md:grid-cols-[240px_1fr]`}>
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
                      [before[r.bug], r].map((row, j) => (
                        <Cell key={`${k}${j}`} row={row} k={k} ours={data.ours[r.bug]} size="sm" title={`${r.bug} ${lab} ${j ? "after" : "before"}`} i={ci * 2 + j * 4} r={li} />
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
