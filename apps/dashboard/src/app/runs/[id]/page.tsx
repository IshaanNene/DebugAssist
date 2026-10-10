import Link from "next/link";
import { api } from "@/lib/api";
import type { Call, Decision, RunDetail } from "@/lib/types";
import { ApiDown, Badge, Card, priorityTone } from "@/components/ui";
import { DecisionLedger } from "@/components/DecisionLedger";
import { RunLive } from "@/components/RunLive";

function CostTable({ costs, decisions }: { costs: Record<string, number>; decisions: Decision[] }) {
  const clef = new Map<string, number>();
  for (const d of decisions) clef.set(d.decision_id, (clef.get(d.decision_id) ?? 0) + d.cost_usd);
  const llmTotal = Object.values(costs).reduce((a, b) => a + b, 0);
  const clefTotal = [...clef.values()].reduce((a, b) => a + b, 0);
  const rows: [string, number, string][] = [
    ...Object.entries(costs).map(([k, v]) => [k, v, "LLM"] as [string, number, string]),
    ...[...clef.entries()].map(([k, v]) => [k, v, "Clef"] as [string, number, string]),
  ].sort((a, b) => b[1] - a[1]);
  return (
    <table className="w-full text-xs">
      <tbody>
        {rows.map(([k, v, kind]) => (
          <tr key={`${kind}-${k}`} className="border-t border-line">
            <td className="py-1 font-mono">{k}</td>
            <td><Badge tone={kind === "LLM" ? "blue" : "amber"}>{kind}</Badge></td>
            <td className="text-right">${v.toFixed(5)}</td>
          </tr>
        ))}
        <tr className="border-t border-line font-semibold">
          <td className="py-1">total</td>
          <td className="text-muted">LLM ${llmTotal.toFixed(4)} · Clef ${clefTotal.toFixed(4)}</td>
          <td className="text-right">${(llmTotal + clefTotal).toFixed(4)}</td>
        </tr>
      </tbody>
    </table>
  );
}

export default async function RunPage(props: PageProps<"/runs/[id]">) {
  const { id } = await props.params;
  const [run, decisions, calls] = await Promise.all([
    api<RunDetail>(`/api/runs/${id}`),
    api<Decision[]>(`/api/runs/${id}/decisions`),
    api<Call[]>(`/api/runs/${id}/calls`),
  ]);
  if (!run) return <ApiDown />;
  const s = run.state;
  const llmNodes: [string, Record<string, unknown>][] = [
    ...(s.rca?.llm ? ([["classify_rca", s.rca.llm]] as [string, Record<string, unknown>][]) : []),
    ...s.fix_attempts.flatMap((fa) => Object.entries(fa.llm).map(([k, v]) => [k, v] as [string, Record<string, unknown>])),
    ...(s.rca?.subagents ?? []).map((a) => [`subagent ${a.id}`, a as unknown as Record<string, unknown>] as [string, Record<string, unknown>]),
  ];
  const lanes = (s.rca?.subagents ?? []).map((a) => ({ id: a.id, status: a.status }));
  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted">
          <span className="font-mono">{id}</span>
          {s.triage && <Badge tone={priorityTone(s.triage.priority)}>{s.triage.priority}</Badge>}
          <Link href={`/issues/${s.issue?.source}/${s.issue?.id}`} className="text-llm hover:underline">{s.issue?.id} RCA →</Link>
          {s.fix_attempts.length > 0 && <Link href={`/runs/${id}/pr`} className="text-llm hover:underline">PR panel →</Link>}
          <a href={run.phoenix_url} className="hover:underline" title={run.phoenix_trace ? "this run's trace in Phoenix" : "this run has no trace (Phoenix was off)"}>
            {run.phoenix_trace ? `Phoenix trace ↗${run.traces.length > 1 ? ` (latest of ${run.traces.length})` : ""}` : "Phoenix ↗"}
          </a>
          {run.langfuse_url && (
            <a href={run.langfuse_url} className="hover:underline" title="this run's trace in Langfuse (if it was exported there)">
              Langfuse trace ↗
            </a>
          )}
        </div>
        <h1 className="text-xl font-semibold">{s.issue?.title}</h1>
      </header>
      <RunLive runId={id} summary={run.summary} graph={run.graph} calls={calls ?? []} lanes={lanes} />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Card title={`Decision ledger (${decisions?.length ?? 0})`}>
          <DecisionLedger decisions={decisions ?? []} />
        </Card>
        <div className="space-y-4">
          <Card title="LLM nodes · turns and cost">
            <table className="w-full text-xs">
              <thead className="text-left text-muted">
                <tr><th className="pb-1">node</th><th>status</th><th className="text-right">turns</th><th className="text-right">cost</th></tr>
              </thead>
              <tbody>
                {llmNodes.map(([name, l]) => (
                  <tr key={name} className="border-t border-line">
                    <td className="py-1 font-mono">{name}</td>
                    <td>{String(l.status ?? "–")}</td>
                    <td className="text-right">{String(l.turns ?? "–")}</td>
                    <td className="text-right">{typeof l.cost_usd === "number" ? `$${l.cost_usd.toFixed(4)}` : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-muted">Turn caps come from the agent type (configs/agent_types).</p>
          </Card>
          <Card title="Cost by node">
            <CostTable costs={s.costs} decisions={decisions ?? []} />
          </Card>
          {s.errors.length > 0 && (
            <Card title="Errors">
              <pre className="max-h-60 overflow-auto whitespace-pre-wrap text-xs text-red-500">{s.errors.slice(0, 2).join("\n\n")}</pre>
            </Card>
          )}
          {s.notifications.length > 0 && (
            <Card title="Notifications">
              <ul className="space-y-1 text-xs">
                {s.notifications.map((n, i) => (
                  <li key={i}>
                    <Badge>{String(n.kind)}</Badge> {String(n.title ?? n.detail ?? n.url ?? n.to ?? "")}{" "}
                    <span className="text-muted">{n.mode ? `(${String(n.mode)})` : n.result ? `(${String(n.result)})` : ""}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
