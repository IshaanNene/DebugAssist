import Link from "next/link";
import { api } from "@/lib/api";
import type { Call, Decision, RunDetail } from "@/lib/types";
import { ApiDown, Badge, Card, priorityTone } from "@/components/ui";
import { DecisionLedger } from "@/components/DecisionLedger";
import { RunLive } from "@/components/RunLive";

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
          <a href={run.phoenix_url} className="hover:underline" title="Per-run traces arrive with the observability phase">Phoenix ↗</a>
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
