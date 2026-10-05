import Link from "next/link";
import { api } from "@/lib/api";
import type { RunDetail, RunSummary } from "@/lib/types";
import { ApiDown, Badge, Card, Empty, outcomeTone, pct, priorityTone, Prose } from "@/components/ui";
import { Reactions } from "@/components/Reactions";

const GROUNDING = {
  supported: { tone: "green", label: "grounded" },
  unverified: { tone: "amber", label: "unverified" },
  unsupported: { tone: "red", label: "dropped" },
} as const;

export default async function IssuePage(props: PageProps<"/issues/[source]/[id]">) {
  const { source, id } = await props.params;
  const runs = await api<RunSummary[]>(`/api/runs?issue=${encodeURIComponent(id)}`);
  if (runs === null) return <ApiDown />;
  const latest = runs.find((r) => r.status !== "failed" && r.category) ?? runs[0];
  const run = latest ? await api<RunDetail>(`/api/runs/${latest.run_id}`) : null;
  const s = run?.state;
  const o = s?.rca?.output;
  const grounding = new Map((s?.rca?.grounding ?? []).map((g) => [g.text, g]));
  const evidence = new Map((s?.evidence ?? []).map((e) => [e.id, e]));
  const cat = s?.rca?.category_decision as { p?: number; chosen?: Record<string, unknown> } | undefined;
  const fa = s?.fix_attempts?.at(-1);

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <div className="flex items-center gap-2 text-sm text-muted">
          <Badge tone={source === "vitals" ? "red" : "blue"}>{source === "vitals" ? "Vitals" : "BugDrop"}</Badge>
          <span className="font-mono">{id}</span>
          {s?.issue?.url && (
            <a href={s.issue.url} className="hover:underline">open in {source === "vitals" ? "Vitals" : "BugDrop"} ↗</a>
          )}
          {runs.length > 1 && <span>· {runs.length} runs</span>}
        </div>
        <h1 className="text-2xl font-semibold">{s?.issue?.title ?? latest?.title ?? id}</h1>
        {s?.triage && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Badge tone={priorityTone(s.triage.priority)}>{s.triage.priority}</Badge>
            <Badge>{s.triage.severity}</Badge>
            <span className="text-muted">{s.triage.owner_team} · on-call @{s.triage.oncall}</span>
            {latest && (
              <Link href={`/runs/${latest.run_id}`} className="text-llm hover:underline">run {latest.run_id} →</Link>
            )}
          </div>
        )}
      </header>

      {!o ? (
        <Empty>No root-cause analysis for this issue yet{latest ? ` (latest run: ${latest.status})` : ""}.</Empty>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="space-y-4">
            <Card title="Root cause" right={latest && <Reactions runId={latest.run_id} target="rca" />}>
              <p className="font-medium"><Prose text={o.summary} /></p>
              <div className="mt-3 flex flex-wrap gap-2 text-xs">
                <Badge tone="blue">{o.category}</Badge>
                {cat?.p != null && <Badge title="Clef D5 probability for the category">confidence {pct(cat.p)}</Badge>}
                {s?.rca?.actionable === false && <Badge tone="amber">routed (not a code fix)</Badge>}
              </div>
              <p className="mt-3 text-sm"><Prose text={o.root_cause} /></p>
              <dl className="mt-3 space-y-1 text-sm">
                <div>
                  <dt className="inline text-muted">Location </dt>
                  <dd className="inline font-mono text-xs">
                    {o.location.file} → {o.location.function}
                    {o.location.line ? `:${o.location.line}` : ""}
                  </dd>
                </div>
                {(s?.fix_plan?.suspect_commits?.length ?? 0) > 0 ? (
                  <div>
                    <dt className="inline text-muted">Introduced by </dt>
                    <dd className="inline font-mono text-xs">
                      {s!.fix_plan!.suspect_commits.map((c) => `${c.sha} ${c.subject}`).join("; ")}
                    </dd>
                  </div>
                ) : (
                  o.suspect_commit && (
                    <div><dt className="inline text-muted">Introduced by </dt><dd className="inline font-mono text-xs">{o.suspect_commit}</dd></div>
                  )
                )}
                {o.implicated_flag && (
                  <div><dt className="inline text-muted">Behind flag </dt><dd className="inline font-mono text-xs">{o.implicated_flag}</dd></div>
                )}
              </dl>
            </Card>

            <Card title="Key facts">
              <ul className="space-y-2 text-sm">
                {o.claims.map((c, i) => {
                  const g = grounding.get(c.text);
                  const badge = g ? GROUNDING[g.grounding] : null;
                  return (
                    <li key={i} className="flex flex-col gap-1">
                      <div className="flex items-start gap-2">
                        {badge && (
                          <Badge tone={badge.tone} title={g?.p != null ? `Clef D9 p=${g.p}` : undefined}>{badge.label}</Badge>
                        )}
                        <span><Prose text={c.text} /></span>
                      </div>
                      <div className="flex flex-wrap items-center gap-1 pl-1">
                        {c.evidence_ids.map((e) => (
                          <a key={e} href={`#${e}`} className="font-mono text-[11px] text-muted hover:underline" title={evidence.get(e)?.summary}>
                            {e}
                          </a>
                        ))}
                        {latest && <Reactions runId={latest.run_id} target={`claim:${i}`} compact />}
                      </div>
                    </li>
                  );
                })}
              </ul>
              {(s?.rca?.dropped_claims?.length ?? 0) > 0 && (
                <p className="mt-3 text-xs text-muted">{s!.rca!.dropped_claims!.length} claim(s) dropped by the grounding check (D9).</p>
              )}
            </Card>

            <Card title="Mitigation · fix">
              <p className="text-sm">{s?.mitigation?.detail ?? "No mitigation."}</p>
              {fa?.output ? (
                <div className="mt-3 text-sm">
                  <p className="font-medium">{fa.output.commit_title}</p>
                  <p className="text-muted">{fa.output.summary}</p>
                </div>
              ) : (
                <p className="mt-3 text-sm text-muted">{s?.fix_plan?.skip ?? "No fix produced."}</p>
              )}
              <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
                {s?.ship && <Badge tone={outcomeTone(s.ship.outcome)}>{s.ship.outcome}</Badge>}
                {s?.validation?.passed && <Badge tone="green">validated · {fa?.tier}</Badge>}
                {s?.pr && (
                  <a href={s.pr.url} className="text-llm hover:underline">{s.pr.draft ? "draft PR" : "PR"} #{s.pr.number} ↗</a>
                )}
                {latest && s?.fix_attempts?.length ? (
                  <Link href={`/runs/${latest.run_id}/pr`} className="text-llm hover:underline">diff &amp; proof →</Link>
                ) : null}
              </div>
            </Card>
          </div>

          <div className="space-y-4">
            <Card title="Evidence timeline">
              <ol className="relative space-y-3 border-l border-line pl-4">
                {o.timeline.map((t, i) => (
                  <li key={i} className="text-sm">
                    <span className="absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full border border-line bg-panel" />
                    <div className="font-mono text-xs text-muted">{t.when}</div>
                    <div><Prose text={t.event} /></div>
                    <div className="flex flex-wrap gap-1">
                      {t.evidence_ids.map((e) => (
                        <a key={e} href={`#${e}`} className="font-mono text-[11px] text-muted hover:underline">{e}</a>
                      ))}
                    </div>
                  </li>
                ))}
              </ol>
            </Card>
            <Card title={`Evidence (${s?.evidence.length ?? 0})`}>
              <ul className="space-y-1 text-xs">
                {(s?.evidence ?? []).map((e) => (
                  <li key={e.id} id={e.id} className="flex gap-2 rounded px-1 py-0.5 target:bg-amber-500/15">
                    <Badge>{e.source}</Badge>
                    <span className="truncate">{e.summary}</span>
                    <span className="ml-auto shrink-0 font-mono text-muted">{e.id}</span>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
