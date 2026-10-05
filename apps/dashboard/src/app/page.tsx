import Link from "next/link";
import { api } from "@/lib/api";
import type { Issue } from "@/lib/types";
import { ApiDown, Badge, Empty, outcomeTone, pct, priorityTone, when } from "@/components/ui";

export default async function Inbox() {
  const issues = await api<Issue[]>("/api/issues");
  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">Inbox</h1>
        <p className="text-sm text-muted">Crashes from Vitals and reports from BugDrop, with triage and the latest DebugAssist run.</p>
      </header>
      {issues === null ? (
        <ApiDown />
      ) : issues.length === 0 ? (
        <Empty>No issues yet. Trigger a scenario: <code className="font-mono">make trigger BUG=002</code></Empty>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-line bg-panel">
          <table className="w-full text-sm">
            <thead className="border-b border-line text-left text-xs uppercase text-muted">
              <tr>
                <th className="p-3">Issue</th>
                <th className="p-3">Triage</th>
                <th className="p-3">Owner · on-call</th>
                <th className="p-3">Run</th>
                <th className="p-3">Opened</th>
              </tr>
            </thead>
            <tbody>
              {issues.map((i) => {
                const r = i.run;
                const clef = r
                  ? `Clef (D1): customer impacting ${pct(r.customer_impacting)} · worth an agent run ${pct(r.worth_agent_run)}`
                  : undefined;
                return (
                  <tr key={`${i.source}-${i.id}`} className="border-b border-line last:border-0 hover:bg-bg">
                    <td className="max-w-xl p-3">
                      <div className="flex items-center gap-2">
                        <Badge tone={i.source === "vitals" ? "red" : "blue"}>{i.source === "vitals" ? "Vitals" : "BugDrop"}</Badge>
                        <Link href={`/issues/${i.source}/${i.id}`} className="font-mono text-xs text-muted hover:underline">
                          {i.id}
                        </Link>
                        {i.status && <span className="text-xs text-muted">{i.status}</span>}
                      </div>
                      <Link href={`/issues/${i.source}/${i.id}`} className="mt-1 block truncate font-medium hover:underline">
                        {i.title}
                      </Link>
                      <div className="text-xs text-muted">
                        {i.app} {i.version}
                        {i.events != null && ` · ${i.events} events`}
                      </div>
                    </td>
                    <td className="p-3" title={clef}>
                      {r?.priority ? (
                        <div className="flex gap-1">
                          <Badge tone={priorityTone(r.priority)}>{r.priority}</Badge>
                          <Badge>{r.severity}</Badge>
                        </div>
                      ) : (
                        <span className="text-muted">–</span>
                      )}
                    </td>
                    <td className="p-3 text-xs">
                      {r?.owner ? (
                        <>
                          <div>{r.owner}</div>
                          <div className="text-muted">@{r.oncall}</div>
                        </>
                      ) : (
                        <span className="text-muted">–</span>
                      )}
                    </td>
                    <td className="p-3">
                      {r ? (
                        <Link href={`/runs/${r.run_id}`} className="flex flex-col gap-1">
                          <Badge tone={outcomeTone(r.outcome ?? r.status)}>{r.outcome ?? r.status}</Badge>
                          <span className="text-xs text-muted">
                            {r.llm_mode} · ${r.cost_usd.toFixed(3)}
                            {r.validated && " · validated"}
                          </span>
                        </Link>
                      ) : (
                        <span className="text-xs text-muted">not run</span>
                      )}
                    </td>
                    <td className="p-3 text-xs text-muted">{when(i.opened_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
