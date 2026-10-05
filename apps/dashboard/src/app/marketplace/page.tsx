import { api } from "@/lib/api";
import { ApiDown, Badge, Card } from "@/components/ui";

interface Market {
  agent_types: Record<string, { description: string; nodes: Record<string, Record<string, unknown>>; skills: string[]; run_budget_usd: number | null }>;
  skills: { name: string; plugin: string; description: string; tokens: number; path: string; used_by: string[] }[];
  subagents: { id: string; description: string; inputs: string[]; mcp_servers: string[] }[];
  templates: { id: string; stage: string; model: string; description: string }[];
}

interface Proposal {
  id: string;
  branch: string;
  skill: string;
  lesson: string;
  title: string;
  run_id: string;
  pushed: boolean;
  patch_lines: number;
}

export default async function Marketplace() {
  const [m, proposals] = await Promise.all([api<Market>("/api/marketplace"), api<Proposal[]>("/api/proposals")]);
  if (!m) return <ApiDown />;
  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">Marketplace &amp; agent types</h1>
        <p className="text-sm text-muted">
          The plan is fixed in code; what changes per agent is skills, subagents and decision templates. Skills are markdown under
          <code className="font-mono"> marketplace/plugins/*/skills</code>.
        </p>
      </header>
      <Card title={`Skills (${m.skills.length})`}>
        <div className="grid gap-3 md:grid-cols-2">
          {m.skills.map((s) => (
            <div key={s.path} className="rounded border border-line p-3">
              <div className="flex items-center gap-2">
                <span className="font-semibold">{s.name}</span>
                <Badge>{s.plugin}</Badge>
                <span className="ml-auto text-xs text-muted">~{s.tokens} tokens</span>
              </div>
              <p className="mt-1 text-sm text-muted">{s.description}</p>
              <p className="mt-2 text-xs">used by: {s.used_by.join(", ") || "–"}</p>
              <p className="font-mono text-[11px] text-muted">{s.path}</p>
            </div>
          ))}
        </div>
      </Card>
      <Card title={`Proposed skill updates (${proposals?.length ?? 0})`}>
        {(proposals?.length ?? 0) === 0 ? (
          <p className="text-sm text-muted">None yet. Review corrections classified as fix approach or style (D18) become proposals here.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {proposals!.map((p) => (
              <li key={p.id} className="rounded border border-line p-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="amber">{p.skill}</Badge>
                  <span className="font-medium">{p.title}</span>
                  <span className="ml-auto font-mono text-xs text-muted">{p.branch}</span>
                </div>
                <p className="mt-1 text-xs">{p.lesson}</p>
                <p className="text-xs text-muted">
                  local branch, not pushed (this repository is outside the write policy) · {p.patch_lines}-line patch · from run {p.run_id}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Agent types">
        {Object.entries(m.agent_types).map(([name, t]) => (
          <div key={name} className="mb-3">
            <div className="flex items-center gap-2"><span className="font-semibold">{name}</span><span className="text-sm text-muted">{t.description}</span>{t.run_budget_usd != null && <Badge>budget ${t.run_budget_usd}</Badge>}</div>
            <table className="mt-2 w-full text-xs">
              <tbody>
                {Object.entries(t.nodes).map(([node, cfg]) => (
                  <tr key={node} className="border-t border-line">
                    <td className="py-1 font-mono">{node}</td>
                    <td className="text-muted">{Object.entries(cfg).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : String(v)}`).join(" · ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </Card>
      <div className="grid gap-4 xl:grid-cols-2">
        <Card title={`RCA subagents (${m.subagents.length})`}>
          <ul className="space-y-2 text-sm">
            {m.subagents.map((s) => (
              <li key={s.id}>
                <span className="font-mono text-xs">{s.id}</span> <span className="text-muted">— {s.description}</span>
                <div className="mt-0.5 flex flex-wrap gap-1">{s.mcp_servers.map((x) => <Badge key={x} tone="blue">{x}</Badge>)}</div>
              </li>
            ))}
          </ul>
        </Card>
        <Card title={`Clef decision templates (${m.templates.length})`}>
          <ul className="space-y-1 text-sm">
            {m.templates.map((t) => (
              <li key={t.id} className="flex gap-2">
                <span className="w-44 shrink-0 font-mono text-xs">{t.id}</span>
                <Badge tone="amber">{t.model}</Badge>
                <span className="text-muted">{t.description}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
