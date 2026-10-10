import type { Results as R, Row } from "@/lib/data";

const TONE: Record<string, string> = {
  cyan: "text-[var(--cyan)]",
  green: "text-good",
  violet: "text-[var(--violet)]",
  amber: "text-warn",
  muted: "text-muted",
};

const LANES: [string, keyof Row & string][] = [
  ["root cause", "rca"],
  ["fix validated", "validated"],
  ["hidden test", "hidden_tests"],
];

function cell(row: Row | undefined, key: string, ours: boolean): { cls: string; label: string } {
  const v = row?.[key] ?? "";
  if (!row || (key === "validated" && !ours)) return { cls: "border border-line bg-transparent", label: "n/a" };
  if (v === "exact" || v === "True") return { cls: "bg-good", label: v === "True" ? "yes" : v };
  if (v === "directional") return { cls: "bg-warn", label: v };
  if (v === "wrong" || v === "False") return { cls: "bg-bad", label: v === "False" ? "no" : v };
  return { cls: "border border-line bg-transparent", label: "n/a" };
}

export function Results({ data }: { data: R }) {
  const before = Object.fromEntries(data.baseline.map((r) => [r.bug, r]));
  const near = (rs: Row[]) => rs.filter((r) => r.rca === "exact" || r.rca === "directional").length;
  const passed = (rs: Row[]) => rs.filter((r) => r.hidden_tests === "True").length;
  return (
    <div className="space-y-8">
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {data.stats.map((s) => (
          <div key={s.label} className="frame p-4">
            <span className="frame-corners" />
            <div className={`text-3xl font-semibold tracking-tight ${TONE[s.tone]}`}>{s.value}</div>
            <div className="mt-1 text-sm text-muted">{s.label}</div>
          </div>
        ))}
      </div>

      <div className="frame p-5 overflow-x-auto">
        <span className="frame-corners" />
        <div className="font-mono text-xs uppercase tracking-wider text-muted mb-4">
          baseline · {data.baseline.length} bugs · {data.model} · one seed
        </div>
        <table className="border-separate border-spacing-1.5">
          <thead>
            <tr>
              <th />
              {data.baseline.map((r) => (
                <th
                  key={r.bug}
                  className={`font-mono text-[11px] font-medium ${data.ours[r.bug] ? "text-muted" : "text-[var(--cyan)]"}`}
                  title={data.ours[r.bug] ? "needs a code fix" : "not our bug: the right answer is routing"}
                >
                  {r.bug.slice(-3)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {LANES.map(([lab, key]) => (
              <tr key={key}>
                <td className="pr-3 text-sm whitespace-nowrap">{lab}</td>
                {data.baseline.map((r) => {
                  const c = cell(r, key, data.ours[r.bug]);
                  return (
                    <td key={r.bug}>
                      <div className={`w-7 h-7 rounded-md ${c.cls}`} title={`${r.bug} ${lab}: ${c.label}`} />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted">
          <Legend cls="bg-good" label="exact / yes" />
          <Legend cls="bg-warn" label="directional (right file or module)" />
          <Legend cls="bg-bad" label="wrong / no" />
          <Legend cls="border border-line" label="not applicable" />
          <span className="text-[var(--cyan)]">cyan ids: not our bug — the right answer is routing, not a fix</span>
        </div>
      </div>

      {data.arms.map((arm) => {
        const prev = arm.rows.map((r) => before[r.bug]).filter(Boolean);
        return (
          <div key={arm.name} className="frame p-5 overflow-x-auto hatch">
            <span className="frame-corners" />
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="text-lg font-semibold">
                Re-run on later code: <span className="mark">{arm.name}</span>
              </h3>
              <span className="font-mono text-xs text-muted">commit {arm.commit}</span>
            </div>
            <p className="mt-1 text-sm text-ink-2">
              Root cause right or close {near(prev)}/{prev.length} → {near(arm.rows)}/{arm.rows.length} · hidden tests
              passing {passed(prev)} → {passed(arm.rows)}
            </p>
            <div className="mt-4 flex flex-wrap gap-6">
              {arm.rows.map((r) => (
                <div key={r.bug}>
                  <div className="font-mono text-xs text-muted text-center mb-1">{r.bug.slice(-3)}</div>
                  <div className="grid grid-cols-2 gap-1">
                    {LANES.map(([lab, key]) =>
                      [before[r.bug], r].map((row, j) => {
                        const c = cell(row, key, data.ours[r.bug]);
                        return (
                          <div
                            key={`${key}-${j}`}
                            className={`w-6 h-6 rounded ${c.cls}`}
                            title={`${r.bug} ${lab} ${j ? "after" : "before"}: ${c.label}`}
                          />
                        );
                      }),
                    )}
                  </div>
                  <div className="font-mono text-[10px] text-muted flex justify-between mt-1">
                    <span>before</span>
                    <span>after</span>
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
      <span className={`inline-block w-3 h-3 rounded-sm ${cls}`} />
      {label}
    </span>
  );
}
