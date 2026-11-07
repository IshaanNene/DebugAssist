import type { Metadata } from "next";
import Link from "next/link";
import { HeroDiagram } from "@/components/Diagrams";
import { ChapterPage, Figure, Section } from "@/components/Page";
import { Receipt } from "@/components/Receipt";
import { RunConsole } from "@/components/RunConsole";
import { facts, featuredRun, results, runTimings } from "@/lib/data";

export const metadata: Metadata = {
  title: "A real run — DebugAssist",
  description: "One evaluated DebugAssist run replayed on its true clock, each figure linked to the file, row and field it comes from.",
};

const TOC = [
  { id: "replay", text: "The replay" },
  { id: "flow", text: "What went in, what came out" },
  { id: "record", text: "The record" },
];

export default function RunPage() {
  const data = results();
  const f = facts();
  const run = featuredRun(data);
  const timings = run ? runTimings(run.runId) : null;
  const csv = `evals/reports/${data.report}/results.csv`;

  return (
    <ChapterPage
      chapter="/run/"
      title={
        <>
          {run ? `${Math.round(run.wallS)} seconds,` : "One run,"} <span className="hl">replayed.</span>
        </>
      }
      lead={
        <>
          An evaluated run on its true clock: solid bars where code acted, hatched where an LLM agent did, a hollow tick for
          each Clef decision. Every underlined figure opens the file, row and field it comes from.
        </>
      }
      sources={[csv, `evals/reports/${data.report}/run-timings.json`]}
      toc={TOC}
    >
      {run && timings ? (
        <>
          <Section id="replay" title="The replay" aside={`${run.issue} · run ${run.runId}`}>
            <div className="fx">
              <RunConsole
                run={run}
                timings={timings}
                report={data.report}
                model={data.model}
                notes={{
                  auto_triage: <>Priority set by Clef, owner from CODEOWNERS.</>,
                  context_collector: <>Evidence bundle from {f.mcpServers} MCP servers: crashes, code, flags, telemetry.</>,
                  classify_rca: (
                    <>
                      Root cause in <span className="font-mono text-[12px] text-t1">{run.location}</span>, with{" "}
                      <Receipt source={{ file: csv, row: `run_id ${run.runId}`, field: "claims · claims_unsupported", raw: `${run.claims} · ${run.unsupported}` }}>
                        {run.claims} claims, {run.unsupported} unsupported
                      </Receipt>
                      .
                    </>
                  ),
                  fix: <>A {run.tier} test fails on the shipped release; the fix makes it pass.</>,
                  validate: (
                    <>
                      Suite green. Hidden test passed: <span className="font-mono text-[12px]">{run.hiddenTest.split("/").pop()}</span>.
                    </>
                  ),
                }}
              />
            </div>
          </Section>

          <Section id="flow" title="What went in, what came out">
            <Figure n="1" title="the run as a system" note={`${run.issue}, an evaluated run`}>
              <HeroDiagram run={run} servers={f.mcpServers} tools={f.mcpTools} templates={f.templates} />
            </Figure>
          </Section>

          <Section id="record" title="The record" aside={csv}>
            <dl className="fx grid gap-px border border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
              {(
                [
                  ["Issue", run.issue, "issue"],
                  ["Bug", run.bug, "bug"],
                  ["Agent", run.agentType, "agent_type"],
                  ["Model", data.model, "model"],
                  ["Root cause", run.location, "rca_location"],
                  ["Claims · unsupported", `${run.claims} · ${run.unsupported}`, "claims · claims_unsupported"],
                  ["Validation tier", run.tier, "tier"],
                  ["Hidden test", run.hiddenTest.split("/").pop() ?? "", "hidden_detail"],
                ] as [string, string, string][]
              ).map(([k, v, field]) => (
                <div key={k} className="min-w-0 bg-surface px-5 py-4">
                  <dt className="label text-[10px] text-t4">{k}</dt>
                  <dd className="mt-1.5 break-words font-mono text-[13px] text-t1">
                    <Receipt source={{ file: csv, row: `run_id ${run.runId}`, field, raw: v }}>{v}</Receipt>
                  </dd>
                </div>
              ))}
            </dl>
            <p className="fx mt-6 max-w-[68ch] text-[14.5px] leading-[1.6] text-t3">
              One run of one bug proves little — seeds disagree on some bugs. The whole catalog, every arm and every seed is in
              the{" "}
              <Link className="text-t1 underline decoration-line-2 underline-offset-[3px] hover:decoration-t1" href="/results/">
                lab notebook
              </Link>
              .
            </p>
          </Section>
        </>
      ) : (
        <p className="pt-24 text-t3">No featured run in the latest report.</p>
      )}
    </ChapterPage>
  );
}
