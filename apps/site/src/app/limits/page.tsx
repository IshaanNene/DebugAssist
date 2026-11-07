import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { Dumbbell, ReplayDots } from "@/components/opsfigs";
import { ChapterPage, Figure, Section } from "@/components/Page";
import { deciderReplay, realBugs, results } from "@/lib/data";
import { claims, decisionOps, wilson } from "@/lib/ops";

export const metadata: Metadata = {
  title: "Limitations — DebugAssist",
  description: "What DebugAssist cannot do yet, each weakness with the evidence from the evaluation reports and what would change it.",
};

const pc = (v: number) => `${Math.round(v * 100)}%`;

/** One limitation: what the reports show, what it means, what would change it. */
function Limit({ n, title, evidence, means, change, children }: { n: number; title: string; evidence: ReactNode; means: ReactNode; change: ReactNode; children?: ReactNode }) {
  return (
    <article className="fx border border-line-strong bg-surface">
      <header className="flex items-baseline gap-4 border-b border-line px-5 py-4 sm:px-6">
        <span className="grid h-[26px] w-[26px] shrink-0 place-items-center border border-t1 font-mono text-[11px] text-t1">{n}</span>
        <h3 className="text-[19px] font-medium tracking-[-0.01em] text-t1">{title}</h3>
      </header>
      {children && <div className="border-b border-line p-5 sm:p-8">{children}</div>}
      <dl className="grid gap-px bg-line md:grid-cols-3">
        {(
          [
            ["the evidence", evidence],
            ["what it means", means],
            ["what would change it", change],
          ] as const
        ).map(([k, v]) => (
          <div key={k} className="bg-surface px-5 py-4 sm:px-6">
            <dt className="font-mono text-[10.5px] uppercase tracking-[0.08em] text-t3">{k}</dt>
            <dd className="mt-2 text-[14.5px] leading-[1.6] text-t2">{v}</dd>
          </div>
        ))}
      </dl>
    </article>
  );
}

export default function LimitsPage() {
  const data = results();
  const c = claims(data);
  const ab = data.ablation;
  const replay = deciderReplay();
  const ops = decisionOps();
  const reals = realBugs();
  const [lo, hi] = wilson(c.near, c.n);
  const SRC = `evals/reports/${data.report}`;

  const gap = ab ? Math.max(...ab.lanes.map((l) => Math.abs(l.clef - l.noClef))) : 0;
  const rulesWin = replay.filter((r) => r.acc.rules !== null && r.acc.rules > Math.max(r.acc.clef ?? 0, r.acc["clef-flash"] ?? 0, r.acc.llm ?? 0));
  const worst = ops ? [...ops.rows].sort((a, b) => a.accAtTau - b.accAtTau)[0] : null;
  const smallest = replay.length ? [...replay].sort((a, b) => a.n - b.n)[0] : null;
  const realRuns = reals.reduce((t, r) => t + r.runs, 0);
  const realHidden = reals.reduce((t, r) => t + r.hidden, 0);
  const realHiddenRan = reals.reduce((t, r) => t + r.hiddenRan, 0);
  const link = (href: string, t: string) => (
    <Link href={href} className="underline decoration-line-2 underline-offset-[3px] hover:text-t1">
      {t}
    </Link>
  );

  return (
    <ChapterPage
      chapter="/limits/"
      title="What it can’t do yet."
      lead="The weaknesses to know before trusting a number on this site. Each is computed from the same reports as the results, with what it means and what would change it."
      sources={[`${SRC}/results.csv`, `${SRC}/e1.csv`, `${SRC}/decisions.csv`, `${SRC}/report.md`]}
      toc={[
        { id: "clef", text: "Clef's edge is not shown" },
        { id: "rules", text: "Some decisions lose to rules" },
        { id: "samples", text: "Small samples" },
        { id: "fixes", text: "Its own test is not enough" },
        { id: "catalog", text: "A catalog we built" },
        { id: "claims", text: "Claims without evidence" },
      ]}
    >
      <Section id="clef" title="Decisions" aside={`Fig. 1 · ${ab?.arm ?? ""}`}>
        <div className="grid gap-8">
          {ab && (
            <Limit
              n={1}
              title="Clef's edge over an LLM decider is not established"
              evidence={
                <>
                  On {ab.bugs} bugs, the same pipeline with an LLM making every decision is within {Math.round(gap * 100)} points of Clef on
                  every lane — Clef at {ab.clefSeeds} seeds per bug, the LLM decider at one.
                </>
              }
              means="The central bet — a calibrated decision model beats an LLM's own confidence — is not shown end to end on this catalog. The gaps come from single bugs and go both ways."
              change={<>Three seeds for the LLM decider, more bugs, and a paired test per bug. See {link("/clef/", "Why Clef")}.</>}
            >
              <Figure n="1" title="pass rates with Clef and with an LLM decider, the same bugs" note={`mean of per-bug rates · ${ab.arm}`}>
                <Dumbbell lanes={ab.lanes} clefSeeds={ab.clefSeeds} />
              </Figure>
            </Limit>
          )}
          {replay.length > 0 && (
            <div id="rules" className="scroll-mt-24">
              <Limit
                n={2}
                title="Some decisions lose to hand-written rules"
                evidence={
                  <>
                    Re-deciding logged decisions, rules beat every model on {rulesWin.map((r) => r.decision.replace(/_.*/, "")).join(" and ")}
                    {rulesWin.length ? "" : "none"}.
                    {worst && (
                      <>
                        {" "}
                        Live, {worst.decision.replace(/_/, " ").replace(/_/g, " ")} acts on {pc(worst.coverage)} of cases and is right on{" "}
                        {pc(worst.accAtTau)} of those.
                      </>
                    )}
                  </>
                }
                means="Where a decision is badly calibrated, its threshold does not protect the run: it acts with confidence it has not earned."
                change="Fix the template where a rule wins (more context, sharper outcomes), or keep the rule. Abstain more on the weakest decision until it improves."
              >
                <Figure n="2" title="each logged decision re-decided by Clef, Clef-flash, an LLM and rules" note={`replay E1 · ${SRC}/e1.csv`}>
                  <ReplayDots rows={replay} />
                </Figure>
              </Limit>
            </div>
          )}
        </div>
      </Section>

      <Section id="samples" title="Measurement" aside={`${c.n} headline runs`}>
        <div className="grid gap-8">
          <Limit
            n={3}
            title="The samples are small"
            evidence={
              <>
                Root cause right or close: {pc(c.near / c.n)} ({c.near} of {c.n} runs), 95% interval {pc(lo)}–{pc(hi)}. The headline has{" "}
                {data.headline.seeds} seeds per bug; the Clef ablation has one for the LLM side
                {smallest ? `; the smallest replay row (${smallest.decision.replace(/_.*/, "")}) has ${smallest.n} cases` : ""}.
              </>
            }
            means="Differences of a few points between configurations are inside the noise. Read every rate on this site with its interval."
            change="More seeds per bug and more bugs; report intervals next to every rate."
          />
          <div id="fixes" className="scroll-mt-24">
            <Limit
              n={4}
              title="Passing its own test is not enough"
              evidence={
                <>
                  In {c.validatedButHiddenFails} of {c.hiddenRan} runs with a hidden test, the fix passed the agent&apos;s own validation and failed
                  the hidden one.
                </>
              }
              means="Fixes tend to be as narrow as the report: they make the reproduced case pass and miss its siblings. Model-based checkers agreed with the narrow fixes."
              change={<>Every fix checked against the cases next to the reported one before it ships; the {link("/results/", "Lab notebook")} has four attempts at that.</>}
            />
          </div>
          <div id="catalog" className="scroll-mt-24">
            <Limit
              n={5}
              title="Most of the evidence is a catalog we built"
              evidence={
                <>
                  {data.catalog.evaluated} of {data.catalog.total} catalog bugs are evaluated, all shipped into MiniRide, an app written for the
                  test bed, and all on one model ({c.models.join(", ")}). Real open-source bugs: {reals.length} cases, {realRuns} runs, the
                  upstream test passing in {realHidden} of {realHiddenRan}.
                </>
              }
              means="The catalog tests the pipeline on bugs whose shape we chose, in a codebase we know. Real repositories are larger, older and were not written to be debugged."
              change={<>More real issues from public repositories, other models, and other codebases. See {link("/testbed/", "Test bed")}.</>}
            />
          </div>
          <div id="claims" className="scroll-mt-24">
            <Limit
              n={6}
              title="Some claims have no evidence behind them"
              evidence={
                <>
                  {c.unsupported} of {c.claims} claims in the headline runs ({pc(c.unsupported / (c.claims || 1))}) are not supported by the evidence
                  they cite.
                </>
              }
              means="The grounding check finds these after the fact; a root cause can still lean on a claim its evidence does not back."
              change="Re-ask or drop a claim the check rejects before the root cause is written, and measure how often that changes the answer."
            />
          </div>
        </div>
      </Section>
    </ChapterPage>
  );
}
