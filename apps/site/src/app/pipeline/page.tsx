import type { Metadata } from "next";
import Link from "next/link";
import { Graph } from "@/components/Graph";
import { Loop } from "@/components/Loop";
import { ChapterPage, Figure, Section } from "@/components/Page";
import { featuredRun, results, runTimings } from "@/lib/data";
import { templates } from "@/lib/docs";

export const metadata: Metadata = {
  title: "Pipeline — DebugAssist",
  description: "Ten steps in a fixed order: who acts at each, which Clef decisions it takes, and how long it took in a real run.",
};

const TOC = [
  { id: "phases", text: "Four phases" },
  { id: "graph", text: "The graph" },
  { id: "stages", text: "Decisions by step" },
];

export default function PipelinePage() {
  const data = results();
  const run = featuredRun(data);
  const timings = run ? runTimings(run.runId) : null;
  const ms = Object.fromEntries((timings?.steps ?? []).map((s) => [s.node, s.ms]));
  const tpl = templates();
  const stages = [...new Set(tpl.map((t) => t.stage))];

  return (
    <ChapterPage
      chapter="/pipeline/"
      title={
        <>
          Investigate, fix, prove — <span className="hl">in that order.</span>
        </>
      }
      lead={
        <>
          The pipeline is a static graph in code: ten nodes, always the same sequence, with two branches the spec defines —
          a bounded retry from validation back to the fix, and the root cause routing a bug that isn&apos;t ours. Models
          work inside nodes; they never pick the next one.
        </>
      }
      sources={["packages/pipeline/src/debugassist/pipeline/graph.py", "docs/adr/0001-fixed-plan.md", `evals/reports/${data.report}/run-timings.json`]}
      toc={TOC}
    >
      <Section id="phases" title="Four phases" aside="scroll through it">
        <Loop />
      </Section>

      <Section id="graph" title="The graph" aside={run ? `timings from ${run.issue}` : undefined}>
        <Figure n="1" title="the graph, node by node" note="pick a step">
          <Graph ms={ms} runLabel={run ? `run ${run.issue}` : "the featured run"} />
        </Figure>
      </Section>

      <Section id="stages" title="Decisions by step" aside={`${tpl.length} templates · ${stages.length} steps`}>
        <div className="fx grid gap-px border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
          {stages.map((st) => (
            <div key={st} className="bg-surface p-5">
              <div className="font-mono text-[12px] text-t1">{st}</div>
              <ul className="mt-3 space-y-1.5">
                {tpl
                  .filter((t) => t.stage === st)
                  .map((t) => (
                    <li key={t.id}>
                      <Link href={`/decisions/#${t.id}`} className="group flex items-baseline gap-3 text-[14px] text-t2 hover:text-t1">
                        <span className="w-8 shrink-0 font-mono text-[11.5px] text-t3 group-hover:text-t1">{t.id}</span>
                        {t.name}
                      </Link>
                    </li>
                  ))}
              </ul>
            </div>
          ))}
        </div>
      </Section>
    </ChapterPage>
  );
}
