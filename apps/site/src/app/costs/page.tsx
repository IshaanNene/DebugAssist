import type { Metadata } from "next";
import Link from "next/link";
import { CostBars, LatencyRanges } from "@/components/opsfigs";
import { ChapterPage, Figure, Section } from "@/components/Page";
import { results } from "@/lib/data";
import { decisionOps, economics, limits } from "@/lib/ops";

export const metadata: Metadata = {
  title: "Cost and latency — DebugAssist",
  description: "What a DebugAssist run costs and how long it takes, computed from the evaluation reports: per-run cost, time to a root cause, Clef latency and the caps that bound a run.",
};

const usd = (v: number) => `$${v.toFixed(3)}`;
const min = (s: number) => `${(s / 60).toFixed(1)} min`;

export default function CostsPage() {
  const data = results();
  const e = economics(data);
  const ops = decisionOps();
  const lim = limits();
  const rca = lim.nodes.find((n) => n.node === "classify_rca");
  const fix = lim.nodes.find((n) => n.node === "fix");
  const SRC = `evals/reports/${data.report}/results.csv`;

  const tiles: [string, string, string][] = [
    [usd(e.usd.p50), "median cost per run", `p90 ${usd(e.usd.p90)} · most ${usd(e.usd.max)}`],
    [`${Math.round(e.llmShare * 100)}%`, "of spend is the LLM", "the rest is Clef"],
    [min(e.toRca.p50), "discovery → root cause", `p90 ${min(e.toRca.p90)}`],
    [min(e.pipeline.p50), "pipeline time", `p90 ${min(e.pipeline.p90)}`],
    [String(e.turns.p50), "model turns per run", `p90 ${e.turns.p90}`],
    [usd(e.total).replace(/0$/, ""), `all ${e.runs} runs`, `${e.bugs} bugs`],
  ];

  return (
    <ChapterPage
      chapter="/costs/"
      title="What a run costs, and how long it takes."
      lead={
        <>
          Computed at build time from the {e.runs} headline runs ({e.bugs} bugs, {data.headline.seeds} seeds each) in{" "}
          <code className="font-mono text-[0.9em]">evals/reports/{data.report}</code>, and from the caps in{" "}
          <code className="font-mono text-[0.9em]">configs/</code>. Medians with the 90th percentile, because the tail is what you budget for.
        </>
      }
      sources={[SRC, ...(ops ? [`evals/reports/${ops.report}/decisions.csv`] : []), "configs/agent_types/", "configs/subagents.yaml"]}
      toc={[
        { id: "summary", text: "At a glance" },
        { id: "spend", text: "Where the money goes" },
        { id: "latency", text: "Decision latency" },
        { id: "caps", text: "What bounds a run" },
        { id: "failure", text: "When a dependency fails" },
      ]}
    >
      <Section id="summary" title="At a glance" aside={`${e.runs} runs · ${SRC}`}>
        <div className="fx grid border border-line-strong bg-surface sm:grid-cols-3 xl:grid-cols-6">
          {tiles.map(([v, l, s], i) => (
            <div key={l} className={`p-5 ${i ? "border-t border-line sm:border-l sm:border-t-0" : ""} ${i === 3 ? "sm:border-l-0 sm:border-t xl:border-l xl:border-t-0" : ""} ${i > 3 ? "sm:border-t xl:border-t-0" : ""}`}>
              <div className="font-display text-[30px] font-medium tracking-[-0.03em] text-t1">{v}</div>
              <div className="mt-1 text-[13px] text-t2">{l}</div>
              <div className="mt-2 font-mono text-[11px] text-t3">{s}</div>
            </div>
          ))}
        </div>
        <p className="mt-6 max-w-[70ch] text-[15px] leading-[1.65] text-t2">
          Time to a root cause starts when the issue is discovered (Vitals or BugDrop raises it), so it includes the wait for
          traffic to surface the bug; pipeline time is the agent&apos;s own work. {e.toRca.n < e.runs && `${e.runs - e.toRca.n} runs have no discovery timestamp and are left out of that figure.`}
        </p>
      </Section>

      <Section id="spend" title="Where the money goes" aside="Fig. 1">
        <Figure n="1" title="the cost of every headline run, LLM and Clef stacked" note={SRC}>
          <CostBars runs={e.perRun} p50={e.usd.p50} p90={e.usd.p90} />
        </Figure>
        <p className="mt-8 max-w-[70ch] text-[15px] leading-[1.65] text-t2">
          The LLM agents — root cause, reproduction and fix — are {Math.round(e.llmShare * 100)}% of the spend; every Clef decision in
          a run together is the rest. The dearest run cost {usd(e.usd.max)}, {Math.round(e.usd.max / e.usd.p50)}× the median; the 90th percentile is{" "}
          {usd(e.usd.p90)}.
        </p>
      </Section>

      {ops && (
        <Section id="latency" title="Decision latency" aside={`Fig. 2 · evals/reports/${ops.report}/decisions.csv`}>
          <Figure n="2" title="each live Clef decision, median to 95th percentile" note={`${ops.rows.reduce((t, r) => t + r.n, 0)} decisions`}>
            <LatencyRanges rows={ops.rows} />
          </Figure>
          <p className="mt-8 max-w-[70ch] text-[15px] leading-[1.65] text-t2">
            Every Clef decision is a network call to Workers AI. Medians sit between {Math.min(...ops.rows.map((r) => r.p50)).toFixed(1)} and{" "}
            {Math.max(...ops.rows.map((r) => r.p50)).toFixed(1)} s; the slowest 95th percentile is {Math.max(...ops.rows.map((r) => r.p95)).toFixed(1)} s.
            The costs are per thousand calls. See <Link href="/clef/" className="underline decoration-line-2 underline-offset-[3px] hover:text-t1">Why Clef</Link> for what each decision is worth.
          </p>
        </Section>
      )}

      <Section id="caps" title="What bounds a run" aside="configs/agent_types/ · configs/subagents.yaml">
        <div className="fx overflow-x-auto border border-line-strong bg-surface">
          <table className="w-full min-w-[560px] text-left text-[14px]">
            <thead className="border-b border-line font-mono text-[11px] uppercase tracking-[0.06em] text-t3">
              <tr>
                <th className="px-5 py-3 font-normal">who</th>
                <th className="px-5 py-3 font-normal">turns</th>
                <th className="px-5 py-3 font-normal">tool calls</th>
                <th className="px-5 py-3 font-normal">budget</th>
                <th className="px-5 py-3 font-normal">wall clock</th>
              </tr>
            </thead>
            <tbody className="font-mono text-[13px] text-t2">
              {lim.nodes.map((n) => (
                <tr key={n.node} className="border-b border-line">
                  <td className="px-5 py-3 text-t1">{n.node} agent</td>
                  <td className="px-5 py-3">{n.turns}</td>
                  <td className="px-5 py-3">{n.tools}</td>
                  <td className="px-5 py-3">${n.usd}</td>
                  <td className="px-5 py-3 text-t4">—</td>
                </tr>
              ))}
              <tr>
                <td className="px-5 py-3 text-t1">each subagent · up to {lim.subagents.parallel} at once</td>
                <td className="px-5 py-3">{lim.subagents.turns}</td>
                <td className="px-5 py-3">{lim.subagents.tools}</td>
                <td className="px-5 py-3">${lim.subagents.usd}</td>
                <td className="px-5 py-3">{lim.subagents.wall} s</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="mt-6 max-w-[70ch] text-[15px] leading-[1.65] text-t2">
          The same caps in all {lim.agentTypes} agent types. An agent stops before the model call that would cross its budget. The dearest
          headline run cost {usd(e.usd.max)} in all
          {rca && fix ? `, against $${rca.usd} for the root-cause agent and $${fix.usd} for the fix agent alone` : ""}: the caps are a guard
          against a runaway loop, not a limit the runs press against.
        </p>
      </Section>

      <Section id="failure" title="When a dependency fails" aside="configs/deciders.yaml · configs/policies/writes.yaml">
        <ul className="fx grid gap-px border border-line-strong bg-line sm:grid-cols-3">
          {[
            ["Clef unreachable", "Rate limits, server errors and timeouts are retried; if they persist, a circuit breaker opens and the LLM decider answers instead, recorded as such in the decision ledger.", "/clef/"],
            ["Provider or infrastructure fault", "A run that fails on the provider, the sandbox or the network is not counted as an agent mistake: the report lists it under its exclusions and the run is repeated.", "/results/"],
            ["Policy or API unreachable", "A write action not in writes.yaml is a dry run; a GitHub App write is refused if its API cannot be reached.", "/safety/"],
          ].map(([t, d, href]) => (
            <li key={t} className="bg-surface p-5">
              <div className="text-[16px] font-medium text-t1">{t}</div>
              <p className="mt-2 text-[14px] leading-[1.6] text-t2">{d}</p>
              <Link href={href} className="mt-3 inline-block font-mono text-[11.5px] text-t3 underline decoration-line-2 underline-offset-[3px] hover:text-t1">
                {href}
              </Link>
            </li>
          ))}
        </ul>
      </Section>
    </ChapterPage>
  );
}
