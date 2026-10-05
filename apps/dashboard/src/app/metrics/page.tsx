import { api } from "@/lib/api";
import { ApiDown, Badge, Card } from "@/components/ui";

interface ModeStats {
  runs: number;
  outcomes: Record<string, number>;
  rca_produced: number;
  validated_fixes: number;
  prs: number;
  resolved_after_deploy: number;
  time_to_rca_s_median: number | null;
  time_to_pr_s_median: number | null;
  cost_per_rca_usd_median: number | null;
}
interface DecisionStats {
  decision_id: string;
  description: string | null;
  model: string | null;
  n: number;
  backends: Record<string, number>;
  bands: Record<string, number>;
  latency_p50: number | null;
  latency_p95: number | null;
  usd_per_1k: number;
  labelled: number;
  accuracy: number | null;
  brier: number | null;
}
interface Metrics {
  impact: { by_llm_mode: Record<string, ModeStats>; note: string };
  decisions: DecisionStats[];
}

function Stat({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div className="rounded border border-line p-3">
      <div className="text-xs text-muted">{label}</div>
      <div className="text-xl font-semibold">{value ?? "–"}</div>
    </div>
  );
}

const BAND_COLOR: Record<string, string> = { act: "bg-emerald-500", escalate: "bg-amber-500", safe_default: "bg-zinc-400", per_item: "bg-blue-500" };

export default async function MetricsPage() {
  const m = await api<Metrics>("/api/metrics");
  if (!m) return <ApiDown />;
  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">Metrics</h1>
        <p className="text-sm text-muted">Computed from the runs and the decision ledger on this machine. {m.impact.note}</p>
      </header>
      {Object.entries(m.impact.by_llm_mode).map(([mode, s]) => (
        <Card key={mode} title={`Pipeline · LLM ${mode} runs`} right={mode !== "live" && <Badge tone="amber">scripted, not evidence</Badge>}>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-8">
            <Stat label="runs" value={s.runs} />
            <Stat label="RCAs" value={s.rca_produced} />
            <Stat label="validated fixes" value={s.validated_fixes} />
            <Stat label="PRs" value={s.prs} />
            <Stat label="resolved after deploy" value={s.resolved_after_deploy} />
            <Stat label="time to RCA (median)" value={s.time_to_rca_s_median != null ? `${s.time_to_rca_s_median}s` : null} />
            <Stat label="time to PR (median)" value={s.time_to_pr_s_median != null ? `${s.time_to_pr_s_median}s` : null} />
            <Stat label="cost per RCA (median)" value={s.cost_per_rca_usd_median != null ? `$${s.cost_per_rca_usd_median}` : null} />
          </div>
          <div className="mt-3 flex flex-wrap gap-1 text-xs">
            {Object.entries(s.outcomes).map(([k, v]) => <Badge key={k}>{k}: {v}</Badge>)}
          </div>
        </Card>
      ))}
      <Card title="Decision quality per D#">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-left text-muted">
              <tr>
                <th className="p-2">decision</th><th className="p-2 text-right">n</th><th className="p-2">bands</th>
                <th className="p-2">backends</th><th className="p-2 text-right">p50 / p95</th><th className="p-2 text-right">$ / 1k</th>
                <th className="p-2 text-right">accuracy</th><th className="p-2 text-right">Brier</th>
              </tr>
            </thead>
            <tbody>
              {m.decisions.map((d) => {
                const total = Object.values(d.bands).reduce((a, b) => a + b, 0) || 1;
                return (
                  <tr key={d.decision_id} className="border-t border-line">
                    <td className="p-2"><div className="font-mono">{d.decision_id}</div><div className="text-muted">{d.description}</div></td>
                    <td className="p-2 text-right">{d.n}</td>
                    <td className="p-2">
                      <div className="flex h-2 w-28 overflow-hidden rounded" title={JSON.stringify(d.bands)}>
                        {Object.entries(d.bands).map(([b, n]) => <div key={b} className={BAND_COLOR[b] ?? "bg-zinc-300"} style={{ width: `${(100 * n) / total}%` }} />)}
                      </div>
                    </td>
                    <td className="p-2">{Object.entries(d.backends).map(([b, n]) => `${b} ${n}`).join(" · ")}</td>
                    <td className="p-2 text-right">{d.latency_p50 ?? "–"} / {d.latency_p95 ?? "–"} ms</td>
                    <td className="p-2 text-right">${d.usd_per_1k.toFixed(3)}</td>
                    <td className="p-2 text-right">{d.accuracy ?? <span className="text-muted">needs labels</span>}</td>
                    <td className="p-2 text-right">{d.brier ?? "–"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-muted">
          Accuracy, Brier, calibration (ECE, reliability) and coverage curves need labelled outcomes: the eval harness (P11)
          labels decisions against ground truth and compares Clef, Clef-flash, an LLM baseline and rules.
        </p>
      </Card>
    </div>
  );
}
