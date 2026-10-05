import Link from "next/link";
import { api } from "@/lib/api";
import type { RunSummary } from "@/lib/types";
import { ApiDown, Badge, Empty, outcomeTone, priorityTone, when } from "@/components/ui";

export default async function Runs() {
  const runs = await api<RunSummary[]>("/api/runs");
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Runs</h1>
      {runs === null ? (
        <ApiDown />
      ) : runs.length === 0 ? (
        <Empty>No runs yet: <code className="font-mono">debugassist run VIT-1001</code></Empty>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-line bg-panel">
          <table className="w-full text-sm">
            <thead className="border-b border-line text-left text-xs uppercase text-muted">
              <tr>
                <th className="p-3">Run</th>
                <th className="p-3">Issue</th>
                <th className="p-3">Root cause</th>
                <th className="p-3">Outcome</th>
                <th className="p-3 text-right">Cost · time</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.run_id} className="border-b border-line last:border-0 hover:bg-bg">
                  <td className="p-3">
                    <Link href={`/runs/${r.run_id}`} className="font-mono text-xs hover:underline">{r.run_id}</Link>
                    <div className="text-xs text-muted">{when(r.started_at)} · LLM {r.llm_mode}</div>
                  </td>
                  <td className="max-w-sm p-3">
                    <div className="flex items-center gap-1">
                      {r.priority && <Badge tone={priorityTone(r.priority)}>{r.priority}</Badge>}
                      <span className="font-mono text-xs text-muted">{r.issue_id}</span>
                    </div>
                    <div className="truncate">{r.title}</div>
                  </td>
                  <td className="max-w-xs p-3 text-xs">
                    {r.category && <Badge>{r.category}</Badge>}
                    <div className="mt-1 truncate font-mono text-muted">{r.location ?? "–"}</div>
                  </td>
                  <td className="p-3">
                    <div className="flex flex-wrap gap-1">
                      <Badge tone={outcomeTone(r.outcome ?? r.status)}>{r.outcome ?? r.status}</Badge>
                      {r.validated && <Badge tone="green">validated{r.tier ? ` · ${r.tier}` : ""}</Badge>}
                      {r.watch && <Badge tone={outcomeTone(r.watch)}>{r.watch}</Badge>}
                    </div>
                  </td>
                  <td className="p-3 text-right text-xs text-muted">
                    ${r.cost_usd.toFixed(3)} · {Math.round(r.seconds)}s
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
