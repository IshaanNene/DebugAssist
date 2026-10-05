import Link from "next/link";
import { api, PUBLIC_API_URL } from "@/lib/api";
import type { RunDetail, TestRun } from "@/lib/types";
import { ApiDown, Badge, Card, Empty, outcomeTone } from "@/components/ui";
import { Diff } from "@/components/Diff";
import { AskAi, DiffFixer, OpenInMachine } from "@/components/PostPr";

interface Artifact {
  path: string;
  type: string;
  bytes: number;
}

function Proof({ run, expectFail }: { run: TestRun | null; expectFail?: boolean }) {
  if (!run) return null;
  const ok = expectFail ? run.exit_code !== 0 : run.exit_code === 0;
  return (
    <details className="rounded border border-line">
      <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm">
        <Badge tone={ok ? "green" : "red"}>{ok ? "✓" : "✗"} exit {run.exit_code}</Badge>
        <span>{run.label}</span>
        <code className="ml-auto truncate font-mono text-xs text-muted">{run.command}</code>
      </summary>
      <pre className="max-h-72 overflow-auto border-t border-line bg-bg p-3 text-xs">{run.output_tail}</pre>
    </details>
  );
}

export default async function PrPanel(props: PageProps<"/runs/[id]/pr">) {
  const { id } = await props.params;
  const [run, artifacts] = await Promise.all([
    api<RunDetail>(`/api/runs/${id}`),
    api<Artifact[]>(`/api/runs/${id}/artifacts`),
  ]);
  if (!run) return <ApiDown />;
  const s = run.state;
  const fa = s.fix_attempts.at(-1);
  const v = s.validation;
  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted">
          <Link href={`/runs/${id}`} className="font-mono hover:underline">{id}</Link>
          {s.ship && <Badge tone={outcomeTone(s.ship.outcome)}>{s.ship.outcome}</Badge>}
          {s.pr && <a href={s.pr.url} className="text-llm hover:underline">{s.pr.draft ? "draft " : ""}PR #{s.pr.number} ↗ ({s.pr.mode})</a>}
          {s.pr && <span className="font-mono text-xs">{s.pr.branch} → {s.pr.base}</span>}
        </div>
        <h1 className="text-xl font-semibold">{fa?.output?.commit_title ?? s.issue?.title}</h1>
      </header>
      {!fa ? (
        <Empty>This run produced no fix attempt.</Empty>
      ) : (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <div className="space-y-4">
            <Card title={`Diff · ${fa.files.length} file(s) · attempt ${fa.n}`}>
              <Diff diff={fa.diff} />
            </Card>
          </div>
          <div className="space-y-4">
            <Card title="Validation proof" right={v && <Badge tone={v.passed ? "green" : "red"}>{v.passed ? "passed" : "not passed"}</Badge>}>
              {fa.repro && (
                <p className="mb-3 text-sm">
                  Reproduction <span className="font-mono text-xs">{fa.repro.test_file}</span>{" "}
                  {fa.tier && <Badge tone="blue">{fa.tier}</Badge>}
                  <span className="block text-muted">asserts {fa.repro.asserts}</span>
                </p>
              )}
              <div className="space-y-2">
                <Proof run={v?.failing_before ?? null} expectFail />
                <Proof run={v?.passing_after ?? null} />
                <Proof run={v?.suite ?? null} />
                <Proof run={v?.static ?? null} />
              </div>
              {(artifacts?.length ?? 0) > 0 && (
                <div className="mt-3 space-y-2">
                  <h3 className="text-xs font-semibold uppercase text-muted">Playwright artifacts</h3>
                  {artifacts!.map((a) =>
                    a.type.startsWith("image/") ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img key={a.path} src={`${PUBLIC_API_URL}/api/runs/${id}/artifacts/${a.path}`} alt={a.path} className="rounded border border-line" />
                    ) : a.type.startsWith("video/") ? (
                      <video key={a.path} src={`${PUBLIC_API_URL}/api/runs/${id}/artifacts/${a.path}`} controls className="w-full rounded border border-line" />
                    ) : (
                      <a key={a.path} href={`${PUBLIC_API_URL}/api/runs/${id}/artifacts/${a.path}`} className="block text-xs text-llm hover:underline">
                        {a.path} ({Math.round(a.bytes / 1024)} KB)
                      </a>
                    ),
                  )}
                </div>
              )}
            </Card>
            {(s.post_pr?.length ?? 0) > 0 && (
              <Card title="Review revisions">
                <ul className="space-y-1 text-xs">
                  {s.post_pr!.map((p, i) => (
                    <li key={i}>
                      <Badge tone={p.status === "committed" ? "green" : "red"}>{String(p.status)}</Badge> {String(p.instruction)}
                      {p.commit ? <span className="font-mono text-muted"> → {String(p.commit)}</span> : null}
                    </li>
                  ))}
                </ul>
              </Card>
            )}
            {fa.output && (
              <Card title="Why this fix">
                <p className="text-sm">{fa.output.summary}</p>
                <p className="mt-2 text-sm text-muted">{fa.output.rationale}</p>
                <div className="mt-2 flex gap-2 text-xs"><Badge>{fa.output.strategy}</Badge><Badge tone={fa.output.risk === "low" ? "green" : "amber"}>risk {fa.output.risk}</Badge></div>
              </Card>
            )}
            <DiffFixer runId={id} />
            <AskAi runId={id} />
            <OpenInMachine runId={id} />
          </div>
        </div>
      )}
    </div>
  );
}
