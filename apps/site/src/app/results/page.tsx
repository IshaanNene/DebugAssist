import { Motion, Shortcuts } from "@/components/client";
import { COL, SiteFooter, SiteHeader } from "@/components/Chrome";
import { Results } from "@/components/Results";
import { GH, H2, Lead, Panel, doc } from "@/components/ui";
import {
  bisectReplay,
  contextArms,
  contextAudit,
  deciderReplay,
  fixWidth,
  realBugs,
  results,
  type ContextArm,
} from "@/lib/data";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Lab notebook — DebugAssist",
  description:
    "Every DebugAssist measurement with its report: the bug catalog, Clef against an LLM decider, real open-source bugs, bisect proofs and context-engineering experiments.",
};

const pct = (x: number) => `${Math.round(x * 100)}%`;

// The evaluation in full: everything the home page summarises, each block built from evals/reports.
export default function ResultsPage() {
  const data = results();
  const ctx = contextAudit();
  const replay = deciderReplay();
  const reals = realBugs();
  const fw = fixWidth();
  const bis = bisectReplay();
  const report = doc(`evals/reports/${data.report}/report.md`);
  const v = (i: number) => ({ ["--i" as string]: i });
  // a share in [0, 1] as a whole percent
  const frac = (x: number) => `${Math.round(x * 100)}%`;
  const arms = contextArms();
  // the context-engineering arms, in the order they were measured; fix-quality is the code they re-ran
  const ARM_ORDER = ["fix-quality", "lean", "clear", "compact"];
  const ctxArms = ARM_ORDER.map((n) => arms.find((a) => a.arm === n)).filter((a): a is ContextArm => !!a);
  const before = ctxArms.find((a) => a.arm === "fix-quality");

  return (
    <>
      <Motion />
      <Shortcuts map={{ g: GH, d: doc("README.md") }} />
      <SiteHeader />
      <main>
        {/* ── results ── */}
        <section id="results" className={`${COL} pt-16 md:pt-20`}>
          <div className="label text-t3">Lab notebook</div>
          <h1 className="fx display mt-4 text-[48px] text-t1 sm:text-[72px]">Every measurement, with its report.</h1>
          <Lead className="mt-5">
            {data.catalog.total} bugs injected into a small ride-hailing app as natural-looking release commits —{" "}
            {data.catalog.code} that need a code fix, {data.catalog.notOurs} where the right answer is to route it. The
            agent never sees the answer key; an evaluator scores its root cause and runs hidden tests on its fix.
            {data.catalog.evaluated < data.catalog.total &&
              ` The results cover the first ${data.catalog.evaluated}; the ${data.catalog.total - data.catalog.evaluated} added since have not been run yet.`}{" "}
            Built from{" "}
            <a className="text-t1 underline underline-offset-2" href={report}>
              evals/reports/{data.report}
            </a>
            .
          </Lead>
          <div className="mt-12">
            <Results data={data} />
          </div>
          <div className="mt-2 grid gap-2 md:grid-cols-2">
            <Panel className="fx p-6">
              <div className="label text-good">✓ What works</div>
              <ul className="mt-4 space-y-3 text-[14.5px] leading-[1.55] text-t2">
                <li>Crash-data bugs — locale and currency edge cases, a nil-map panic, a removed await, a battery-draining poller: ten code bugs pass every lane in all three seeds.</li>
                <li>Following a rider&apos;s report into the backend and moving the fix to the service that holds the defect — none of those bugs had the right root cause before the hand-off.</li>
                <li>Saying &ldquo;not our bug&rdquo; — a WebView crash, a vendored SDK, a misconfigured flag, intended behaviour — and routing it instead of patching, for about a cent a run.</li>
              </ul>
            </Panel>
            <Panel className="fx bg-sunk/60 p-6">
              <div className="label text-t3">✗ What doesn&apos;t, yet</div>
              <ul className="caveat mt-4 space-y-3 text-[16.5px] text-t2">
                <li>Stopping where the symptom surfaced: a CORS change and a payments panic are blamed on the client and the gateway.</li>
                <li>Fixes narrower than the regression: they pass the agent&apos;s own test but not the hidden one.</li>
                <li>An active incident still loses to suspicious code, and seeds disagree on ten bugs: one run of a bug proves little.</li>
              </ul>
            </Panel>
          </div>
          {replay.length > 0 && (
            <div id="clef" className="fx panel mt-2 p-6">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div className="font-mono text-[11px] uppercase tracking-[0.04em] text-t3">Does Clef help? Not yet</div>
                <div className="font-mono text-[11px] text-t4">decision replay · accuracy against the catalog</div>
              </div>
              <p className="mt-3 max-w-[80ch] text-[14.5px] leading-[1.55] text-t2">
                The design bets that small calibrated decision models beat an LLM making the same calls. Replaying every
                logged decision with each decider, <b className="font-medium text-t1">Clef does not beat the LLM decider yet</b>,
                and simple rules win on triage and test tier. Those templates are the next thing to fix.
              </p>
              <div className="mt-5 overflow-x-auto">
                <table className="w-full min-w-[520px] text-left text-[13px]">
                  <thead>
                    <tr className="font-mono text-[11px] text-t3">
                      <th className="pb-2 font-normal">decision</th>
                      <th className="pb-2 text-right font-normal">n</th>
                      {(["clef", "clef-flash", "llm", "rules"] as const).map((b) => (
                        <th key={b} className="pb-2 text-right font-normal">
                          {b === "llm" ? "LLM" : b === "rules" ? "rules" : b === "clef" ? "Clef" : "Clef-flash"}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="tabular-nums">
                    {replay.map((d) => {
                      const vals = Object.values(d.acc).filter((v): v is number => v !== null);
                      const best = Math.max(...vals);
                      return (
                        <tr key={d.decision} className="border-t border-line">
                          <td className="py-2 font-mono text-[12px] text-t2">{d.decision.replaceAll("_", " ")}</td>
                          <td className="py-2 text-right text-t3">{d.n}</td>
                          {(["clef", "clef-flash", "llm", "rules"] as const).map((b) => {
                            const v = d.acc[b];
                            return (
                              <td key={b} className={`py-2 text-right ${v !== null && v === best ? "font-medium text-t1" : "text-t3"}`}>
                                {v === null ? "—" : v.toFixed(2)}
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {data.ablation && (
                <div className="mt-6 border-t border-line pt-5">
                  <div className="font-mono text-[11px] uppercase tracking-[0.04em] text-t3">
                    End to end, without Clef · {data.ablation.bugs} bugs · {data.ablation.commit}
                  </div>
                  <p className="mt-2 max-w-[80ch] text-[14px] leading-[1.55] text-t2">
                    The same pipeline with the LLM making every Clef decision ({data.ablation.arm}, one run per bug),
                    against each bug&apos;s latest Clef runs ({data.ablation.clefSeeds} each, on{" "}
                    {data.ablation.clefCommits.join(" and ")}). <b className="font-medium text-t1">A small difference, within noise</b>: the
                    gaps come from a handful of single bugs and go both ways — one escalated to a human by a Clef decision,
                    two not-our-bug cases right only with Clef.
                  </p>
                  <div className="mt-4 grid gap-px bg-line sm:grid-cols-4">
                    {data.ablation.lanes.map((l) => (
                      <div key={l.label} className="bg-raised p-4">
                        <div className="font-display text-[22px] font-medium tabular-nums tracking-[-0.02em] text-t1">
                          {Math.round(100 * l.clef)}% <span className="text-t4">/</span> {Math.round(100 * l.noClef)}%
                        </div>
                        <div className="mt-1 text-[12px] leading-snug text-t3">{l.label} · Clef / no Clef</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
          {reals.length > 0 && (
            <div id="real" className="fx panel mt-2 p-6">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div className="font-mono text-[11px] uppercase tracking-[0.04em] text-t3">
                  Real open-source bugs · {reals.length} {reals.length === 1 ? "case" : "cases"}
                </div>
                <div className="font-mono text-[11px] text-t4">
                  {reals[0].runs} runs each · {reals[0].decider}
                </div>
              </div>
              <p className="mt-3 max-w-[80ch] text-[14.5px] leading-[1.55] text-t2">
                Beyond the synthetic catalog: public issues from small Python libraries, each run on the code it was filed
                against — history cut at that commit, so the upstream fix cannot be found — and scored against the
                fix&apos;s location and its own regression test. Where a report named its own cause, that part was
                withheld.
              </p>
              <div className="mt-5 overflow-x-auto">
                <table className="w-full min-w-[560px] text-left text-[13px]">
                  <thead>
                    <tr className="font-mono text-[11px] text-t3">
                      <th className="pb-2 font-normal">issue</th>
                      <th className="pb-2 text-right font-normal">root cause exact</th>
                      <th className="pb-2 text-right font-normal">fix validated</th>
                      <th className="pb-2 text-right font-normal">upstream test passes</th>
                      <th className="pb-2 text-right font-normal">median cost</th>
                    </tr>
                  </thead>
                  <tbody className="tabular-nums">
                    {reals.map((b) => (
                      <tr key={b.id} className="border-t border-line">
                        <td className="py-2 pr-3">
                          <a className="text-t1 underline underline-offset-2" href={b.issue}>
                            {b.issue.replace("https://github.com/", "").replace("/issues/", "#")}
                          </a>
                          <div className="text-[12px] text-t3">{b.title.replace(/\s*\([^()]*#\d+\)\s*$/, "")}</div>
                        </td>
                        <td className="py-2 text-right text-t2">
                          {b.rcaExact}/{b.runs}
                        </td>
                        <td className="py-2 text-right text-t2">
                          {b.validated}/{b.runs}
                        </td>
                        <td className="py-2 text-right text-t2">
                          {b.hidden}/{b.hiddenRan}
                        </td>
                        <td className="py-2 text-right text-t3">${b.medianUsd.toFixed(3)}</td>
                      </tr>
                    ))}
                    <tr className="border-t border-line-strong font-medium text-t1">
                      <td className="py-2">all {reals.length}</td>
                      <td className="py-2 text-right">
                        {reals.reduce((n, b) => n + b.rcaExact, 0)}/{reals.reduce((n, b) => n + b.runs, 0)}
                      </td>
                      <td className="py-2 text-right">
                        {reals.reduce((n, b) => n + b.validated, 0)}/{reals.reduce((n, b) => n + b.runs, 0)}
                      </td>
                      <td className="py-2 text-right">
                        {reals.reduce((n, b) => n + b.hidden, 0)}/{reals.reduce((n, b) => n + b.hiddenRan, 0)}
                      </td>
                      <td />
                    </tr>
                  </tbody>
                </table>
              </div>
              {bis.length > 0 && (
                <div className="mt-8">
                  <div className="font-mono text-[11px] uppercase tracking-[0.04em] text-t3">
                    Proving the culprit commit · git bisect with the agent&apos;s test
                  </div>
                  <p className="mt-2 max-w-[80ch] text-[14px] leading-[1.55] text-t2">
                    The RCA names the commit that introduced a bug by reading diffs. With bisect on, the validated
                    reproduction test is also run back through history — earlier releases until it passes, then git
                    bisect — no model. Replayed on {bis.reduce((n, b) => n + b.tests, 0)} earlier tests:
                  </p>
                  <ul className="mt-2 max-w-[80ch] space-y-1 text-[13.5px] leading-[1.5] text-t3">
                    {bis.map((b) => (
                      <li key={b.case}>
                        <a className="text-t1 underline underline-offset-2" href={b.issue}>
                          {b.issue.replace("https://github.com/", "").replace("/issues/", "#")}
                        </a>{" "}
                        —{" "}
                        {b.found
                          ? `bisected to ${b.commit} “${b.subject}” in ${b.found}/${b.tests} runs (last good ${b.good}, ${b.steps} steps)${b.rcaAgrees < b.found ? "; the RCA had named another commit" : ""}`
                          : "no earlier release in its history passes the test"}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {fw && fw.checks.length === 3 && (
                <div className="mt-8">
                  <div className="font-mono text-[11px] uppercase tracking-[0.04em] text-t3">
                    Widening narrow fixes · four attempts
                  </div>
                  <p className="mt-2 max-w-[80ch] text-[14px] leading-[1.55] text-t2">
                    The misses on real code were fixes as narrow as the report. Asking a model for wider fixes or
                    wider tests did not change that; a check with no model did, in a replay of every fix made so far.
                  </p>
                  <div className="mt-3 overflow-x-auto">
                    <table className="w-full min-w-[560px] text-left text-[13px]">
                      <thead>
                        <tr className="font-mono text-[11px] text-t3">
                          <th className="pb-2 font-normal">attempt</th>
                          <th className="pb-2 font-normal">model</th>
                          <th className="pb-2 font-normal">what it did to narrow fixes</th>
                          <th className="pb-2 text-right font-normal">upstream / hidden test</th>
                        </tr>
                      </thead>
                      <tbody className="tabular-nums">
                        {[
                          [
                            "Prompt rules for wider tests and fixes",
                            "yes",
                            "nothing — reverted",
                            `${fw.target.after.pass}/${fw.target.after.ran} on cachetools#435`,
                          ],
                          [
                            "A second agent's test, from the report",
                            "yes",
                            `passed ${fw.checks[0].bugs.reduce((n, b) => n + b.second.pass, 0)} of ${fw.checks[0].bugs.reduce((n, b) => n + b.second.ran, 0)} fixes it checked`,
                            `${fw.checks[0].bugs.reduce((n, b) => n + b.hidden.pass, 0)}/${fw.checks[0].bugs.reduce((n, b) => n + b.hidden.ran, 0)}`,
                          ],
                          [
                            "… also shown the repo's other uses",
                            "yes",
                            `sent back ${fw.checks[1].bugs.reduce((n, b) => n + b.rejected, 0)}; every shipped fix still narrow`,
                            `${fw.checks[1].bugs.reduce((n, b) => n + b.hidden.pass, 0)}/${fw.checks[1].bugs.reduce((n, b) => n + b.hidden.ran, 0)}`,
                          ],
                          [
                            "Call variations and introspection",
                            "no",
                            fw.replay
                              ? `live: ${fw.checks[2].bugs.reduce((n, b) => n + b.rejected, 0)} sent back; replay: rejects ${fw.replay.narrow.pass}/${fw.replay.narrow.ran}, no false alarm in ${fw.replay.good.ran}`
                              : `live: ${fw.checks[2].bugs.reduce((n, b) => n + b.rejected, 0)} sent back`,
                            `${fw.checks[2].bugs.reduce((n, b) => n + b.hidden.pass, 0)}/${fw.checks[2].bugs.reduce((n, b) => n + b.hidden.ran, 0)} live`,
                          ],
                        ].map(([a, m, w, t]) => (
                          <tr key={a} className="border-t border-line">
                            <td className="py-2 pr-3 text-t1">{a}</td>
                            <td className="py-2 pr-3 text-t3">{m}</td>
                            <td className="py-2 pr-3 text-t2">{w}</td>
                            <td className="py-2 text-right text-t2">{t}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="mt-2 max-w-[80ch] text-[12.5px] leading-[1.5] text-t4">
                    The live run of the last check predates its introspection part; the replay is of fixes already made,
                    and the introspection part was added after reading upstream&apos;s test. Details below.
                  </p>
                </div>
              )}
              {fw && (
                <p className="mt-5 max-w-[80ch] text-[13.5px] leading-[1.55] text-t3">
                  <span className="text-t2">Widening fixes by prompt didn&apos;t work.</span> Two generic rules — guard
                  the ordinary uses a fix must not break, keep the unit&apos;s contract — re-run on all five: cachetools#435
                  passed upstream&apos;s test in {fw.target.after.pass}/{fw.target.after.ran} runs that made a fix
                  {` (${fw.target.before.pass}/${fw.target.before.ran} before)`}, all five in{" "}
                  {fw.after.pass}/{fw.after.ran}
                  {` (${fw.before.pass}/${fw.before.ran} before)`}. The rules were written with that bug in mind, and
                  were reverted; the runs are in the report as{" "}
                  <code className="font-mono text-[12px]">{fw.arm}</code>.
                </p>
              )}
              {fw?.checks[0] && (
                <p className="mt-3 max-w-[80ch] text-[13.5px] leading-[1.55] text-t3">
                  <span className="text-t2">Nor did a second, independent reproduction.</span> A separate agent wrote
                  its own failing test from the report alone, without the fix or the first test, and the fix had to
                  pass it too. It passed every fix it checked; the hidden tests failed on most:{" "}
                  {fw.checks[0].bugs
                    .map((b) => `${b.bug} ${b.hidden.pass}/${b.hidden.ran} hidden, second test ${b.second.pass}/${b.second.ran}`)
                    .join(" · ")}
                  . Both agents read the same report, and the report shows one example — the other cases the hidden
                  tests check are not in it. Off by default; arm{" "}
                  <code className="font-mono text-[12px]">{fw.checks[0].arm}</code>.
                </p>
              )}
              {fw?.checks[1] && (
                <p className="mt-3 max-w-[80ch] text-[13.5px] leading-[1.55] text-t3">
                  <span className="text-t2">Showing it the code&apos;s other uses made it stricter, not enough.</span>{" "}
                  The checker also saw how the code is used elsewhere in the repository — docs, type stubs, tests,
                  callers, collected by git grep. It sent back {fw.checks[1].bugs.reduce((n, b) => n + b.rejected, 0)}{" "}
                  fixes that had passed their own test, yet no final fix passed the hidden tests:{" "}
                  {fw.checks[1].bugs.map((b) => `${b.bug} ${b.hidden.pass}/${b.hidden.ran} hidden, ${b.rejected} sent back`).join(" · ")}
                  . The repository never calls the method with <code className="font-mono text-[12px]">self=</code>;
                  only upstream&apos;s new test does. Off by default; arm{" "}
                  <code className="font-mono text-[12px]">{fw.checks[1].arm}</code>.
                </p>
              )}
              {fw?.checks[2] && (
                <p className="mt-3 max-w-[80ch] text-[13.5px] leading-[1.55] text-t3">
                  <span className="text-t2">Re-spelling the report&apos;s calls mechanically stopped narrow fixes
                  shipping as validated.</span>{" "}
                  No model: the report&apos;s Python calls are rewritten the other ways a caller can make them (keyword
                  arguments, through the instance or the class), and with the fix every spelling must behave like the
                  reported one. On cachetools#435 it sent back {fw.checks[2].bugs.reduce((n, b) => n + b.rejected, 0)}{" "}
                  fixes; {fw.checks[2].bugs.reduce((n, b) => n + b.validated, 0)}/
                  {fw.checks[2].bugs.reduce((n, b) => n + b.hidden.ran, 0)} runs still validated (every run did before),
                  and that fix handles keyword calls. Upstream&apos;s test still failed (
                  {`${fw.checks[2].bugs.reduce((n, b) => n + b.hidden.pass, 0)}/${fw.checks[2].bugs.reduce((n, b) => n + b.hidden.ran, 0)}`}
                  ) on what the spellings cannot test —{" "}
                  <code className="font-mono text-[12px]">__wrapped__</code> and cache statistics.
                  {fw.replay &&
                    ` Replayed on every earlier fix of the five real bugs — library calls spelled too, from their run-time signatures, and class and instance access compared on __wrapped__, __name__ and __doc__ — it rejects ${fw.replay.narrow.pass} of ${fw.replay.narrow.ran} that upstream's test fails, passes ${fw.replay.good.pass} of ${fw.replay.good.ran} that it passes, and passes upstream's own fix in ${fw.replay.upstream.pass} of ${fw.replay.upstream.ran} — the attribute part was added after reading upstream's test, and only cachetools#435 exercises it.`}{" "}
                  Off by default; arm{" "}
                  <code className="font-mono text-[12px]">{fw.checks[2].arm}</code>.
                </p>
              )}
            </div>
          )}
        </section>

        {/* ── tokens ── */}
        {ctx && (
          <section id="tokens" className={`${COL} pt-[140px]`}>
            <H2>
              Where the tokens go.
            </H2>
            <Lead className="mt-5">
              Every agent turn re-sends the prompt, the tools and the history. A context audit split{" "}
              {(ctx.inputTokens / 1e6).toFixed(1)}M input tokens from real runs by what they carried — so we build the
              context-engineering technique the data points to, not the one that sounds best.
            </Lead>
            <div className="grow panel mt-12 p-6">
              <div className="flex items-baseline justify-between font-mono text-[11px] uppercase tracking-[0.04em] text-t3">
                <span>Every input token, by what it carried</span>
                <span className="normal-case tracking-normal text-t4">{(ctx.inputTokens / 1e6).toFixed(1)}M tokens</span>
              </div>
              <div className="mt-5 flex w-full gap-[3px]">
                {[
                  [ctx.toolsShare, "bg-code", "tool results"],
                  [ctx.prefixShare, "bg-line-strong", "fixed prefix"],
                  [ctx.modelShare, "bg-llm", "model output"],
                ].map(([share, cls, label], i) => (
                  <div key={label as string} className="min-w-0" style={{ flex: `${share as number} 1 0` }}>
                    <div className={`bar h-12 rounded-[3px] ${cls}`} style={v(i * 3)} />
                    <div className="mt-2.5 font-mono text-[20px] font-medium tracking-[-0.02em] text-t1">{frac(share as number)}</div>
                    <div className="truncate text-[12.5px] text-t3">{label}</div>
                  </div>
                ))}
              </div>
            </div>
            <div className="panel mt-2 grid gap-px overflow-hidden bg-line md:grid-cols-[1fr_1.6fr]">
              <div className="bg-raised p-6">
                <div className="font-display text-[56px] font-medium leading-none tracking-[-0.04em]">
                  <span data-count>{frac(ctx.cacheShare)}</span>
                </div>
                <div className="mt-2 text-[13.5px] text-t3">of input served from the prompt cache — the fixed prefix and history are cheap; the volume isn&apos;t.</div>
              </div>
              <div className="grow bg-raised p-6">
                <div className="font-mono text-[11px] uppercase tracking-[0.04em] text-t3">Heaviest tools · share of all input</div>
                <div className="mt-4 space-y-3">
                  {ctx.topTools.map((t, i) => (
                    <div key={t.tool} className="flex items-center gap-3">
                      <span className="w-32 truncate font-mono text-[12px] text-t2">{t.tool}</span>
                      <div className="h-3 flex-1 rounded-[2px] bg-sunk">
                        <div className="bar h-full rounded-[2px] bg-code" style={{ width: `${((t.share / ctx.topTools[0].share) * 100).toFixed(1)}%`, ...v(i) }} />
                      </div>
                      <span className="w-10 text-right font-mono text-[12px] text-t3">{frac(t.share)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            {before && ctxArms.length > 1 && <ArmCompare arms={ctxArms} report={report} />}
          </section>
        )}

      </main>
      <SiteFooter report={report} />
    </>
  );
}

const kTok = (n: number) => (n < 20_000 ? `${(n / 1000).toFixed(1)}K` : `${Math.round(n / 1000)}K`);

const ARM_STYLE: Record<string, { cls: string; what: string }> = {
  "fix-quality": { cls: "bg-t2", what: "the code every experiment re-ran" },
  lean: { cls: "bg-line-strong", what: "file reads capped at 120 lines, an outline tool, long logs offloaded" },
  clear: { cls: "bg-line-strong", what: "old tool results replaced by one-line stubs, in batches" },
  compact: { cls: "bg-line-strong", what: "old steps folded into working notes by the model" },
};

/** The context-engineering arms side by side, from the per-arm context audits. */
function ArmCompare({ arms, report }: { arms: ContextArm[]; report: string }) {
  const metrics: [string, (a: ContextArm) => number, (x: number) => string][] = [
    ["input tokens per agent turn", (a) => a.perTurn, kTok],
    ["input tokens per run", (a) => a.perRun, kTok],
    ["served from the prompt cache", (a) => a.cacheRate, pct],
  ];
  const n = arms.length - 1;
  return (
    <div className="panel mt-2 grid overflow-hidden md:grid-cols-[1fr_1.6fr]">
      <div className="border-b border-line bg-sunk/60 p-6 md:border-b-0 md:border-r">
        <div className="font-mono text-[11px] uppercase tracking-[0.04em] text-t3">Measured · {n} context experiments</div>
        <div className="fx mt-2 font-display text-[24px] font-medium leading-tight tracking-[-0.02em]">
          Fewer tokens isn&apos;t cheaper.
        </div>
        <p className="mt-3 text-[13.5px] leading-[1.55] text-t3">
          Following the audit we tried {n} techniques on the same bugs. Capping reads made agents read more often.
          Clearing old tool results cut tokens per turn, but each clearing rewrites the cached prefix, so the cache hit
          rate fell and cost barely moved. Compacting into notes saved nothing per turn. All four are parked: off by default, with no further work planned.{" "}
          <a className="text-t1 underline underline-offset-2" href={report}>
            Context by arm
          </a>
        </p>
        <ul className="mt-4 space-y-1.5 text-[12.5px] text-t3">
          {arms.map((a) => (
            <li key={a.arm} className="flex gap-2">
              <span className={`mt-[5px] inline-block h-2.5 w-2.5 shrink-0 rounded-[2px] ${ARM_STYLE[a.arm]?.cls ?? "bg-line"}`} />
              <span>
                <b className="font-mono font-normal text-t2">{a.arm}</b> — {ARM_STYLE[a.arm]?.what ?? ""}
                {a.runs < arms[0].runs && (
                  <span className="text-t4">
                    {" "}
                    (partial: {a.runs} of {arms[0].runs} bugs)
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      </div>
      <div className="grow space-y-5 p-6">
        {metrics.map(([label, get, fmt], i) => {
          const max = label.includes("cache") ? 1 : Math.max(...arms.map(get));
          return (
            <div key={label}>
              <div className="mb-1.5 text-[12.5px] text-t2">{label}</div>
              {arms.map((a, j) => (
                <div key={a.arm} className="mt-1 flex items-center gap-3">
                  <span className="w-20 font-mono text-[11px] text-t3">{a.arm}</span>
                  <div className="h-3 flex-1 rounded-[2px] bg-sunk">
                    <div
                      className={`bar h-full rounded-[2px] ${ARM_STYLE[a.arm]?.cls ?? "bg-line"}`}
                      style={{ width: pct(get(a) / max), ["--i" as string]: i * 3 + j }}
                    />
                  </div>
                  <span className="w-12 text-right font-mono text-[12px] text-t2">{fmt(get(a))}</span>
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
