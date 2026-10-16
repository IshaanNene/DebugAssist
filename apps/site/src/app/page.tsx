import { LiveRun, Motion, Shortcuts } from "@/components/client";
import { Architecture } from "@/components/Architecture";
import { Features } from "@/components/Features";
import { Loop } from "@/components/Loop";
import { Results } from "@/components/Results";
import { Box, Button, Dot, GH, H2, Lead, Mark, doc } from "@/components/ui";
import {
  contextArms,
  contextAudit,
  deciderReplay,
  facts,
  featuredRun,
  bisectReplay,
  fixWidth,
  realBugs,
  results,
  type ContextArm,
} from "@/lib/data";

const pct = (x: number) => `${Math.round(x * 100)}%`;
const COL = "mx-auto w-full max-w-[1200px] px-4 sm:px-8";

export default function Home() {
  const data = results();
  const ctx = contextAudit();
  const replay = deciderReplay();
  const reals = realBugs();
  const fw = fixWidth();
  const bis = bisectReplay();
  const foundBisect = bis.find((b) => b.found > 0);
  const f = facts();
  const run = featuredRun(data);
  const latest = data.arms[data.arms.length - 1];
  const pct = (v: number) => (latest?.seeded ? `${v}%` : `${v}`);
  const report = doc(`evals/reports/${data.report}/report.md`);
  const v = (i: number) => ({ ["--i" as string]: i });
  const arms = contextArms();
  // the context-engineering arms, in the order they were measured; fix-quality is the code they re-ran
  const ARM_ORDER = ["fix-quality", "lean", "clear", "compact"];
  const ctxArms = ARM_ORDER.map((n) => arms.find((a) => a.arm === n)).filter((a): a is ContextArm => !!a);
  const before = ctxArms.find((a) => a.arm === "fix-quality");

  return (
    <>
      <Motion />
      <Shortcuts map={{ g: GH, d: doc("README.md"), r: "#results", s: "#start" }} />

      {foundBisect ? (
        <a href="#real" className="group block border-b border-line bg-surface-1 py-2 text-center text-[12.5px] text-t2 hover:text-t1">
          <span className="mr-2 inline-flex h-[18px] items-center bg-t1 px-1.5 font-mono text-[10px] uppercase tracking-[0.05em] text-surface">new</span>
          <span className="font-mono text-[10.5px] uppercase tracking-[0.05em] text-t3">culprit commit, proven</span> ·{" "}
          {foundBisect.issue.replace("https://github.com/", "").replace("/issues/", "#")} bisects to {foundBisect.commit.slice(0, 7)}{" "}
          in {foundBisect.found}/{foundBisect.tests} runs, by running the agent&apos;s test · and a GitHub App for your
          repos · <span className="underline underline-offset-2">see how</span>{" "}
          <span className="inline-block transition-transform group-hover:translate-x-0.5">→</span>
        </a>
      ) : latest?.seeded ? (
        <a href={report} className="group block border-b border-line bg-surface-1 py-2 text-center text-[12.5px] text-t2 hover:text-t1">
          <span className="mr-2 inline-flex h-[18px] items-center bg-t1 px-1.5 font-mono text-[10px] uppercase tracking-[0.05em] text-surface">new</span>
          <span className="font-mono text-[10.5px] uppercase tracking-[0.05em] text-t3">re-run after the fixes</span> · hidden tests
          passing {pct(latest.passed[0])} → {pct(latest.passed[1])} on {latest.bugs.length} bugs ·{" "}
          <span className="underline underline-offset-2">read the report</span>{" "}
          <span className="inline-block transition-transform group-hover:translate-x-0.5">→</span>
        </a>
      ) : before && ctxArms.length > 1 ? (
        <a href={report} className="group block border-b border-line bg-surface-1 py-2 text-center text-[12.5px] text-t2 hover:text-t1">
          <span className="mr-2 inline-flex h-[18px] items-center bg-t1 px-1.5 font-mono text-[10px] uppercase tracking-[0.05em] text-surface">new</span>
          <span className="font-mono text-[10.5px] uppercase tracking-[0.05em] text-t3">context engineering, measured</span> · input
          per turn {ctxArms.map((a) => `${a.arm} ${kTok(a.perTurn)}`).join(" · ")} ·{" "}
          <span className="underline underline-offset-2">read why</span>{" "}
          <span className="inline-block transition-transform group-hover:translate-x-0.5">→</span>
        </a>
      ) : (
        latest && (
          <a href={report} className="group block border-b border-line bg-surface-1 py-2 text-center text-[12.5px] text-t2 hover:text-t1">
            <span className="font-mono text-[10.5px] uppercase tracking-[0.05em] text-t3">re-run · {latest.name}</span> · hidden
            tests passing {pct(latest.passed[0])} → {pct(latest.passed[1])} on {latest.bugs.length} bugs ·{" "}
            <span className="underline underline-offset-2">read the report</span>
          </a>
        )
      )}

      <header className="site-header sticky top-0 z-30 border-b border-line bg-surface/80 backdrop-blur-md">
        <div className={`${COL} flex h-12 items-center justify-between`}>
          <a href="#" className="flex items-center gap-2 font-display text-[15px] font-semibold tracking-[-0.02em]">
            <span className="grid h-5 w-5 place-items-center border border-t1 bg-mark font-mono text-[10px]">D</span>
            DebugAssist
          </a>
          <nav className="hidden gap-6 text-[13px] text-t3 md:flex">
            {[
              ["#how", "How it works"],
              ["#architecture", "Architecture"],
              ["#features", "Features"],
              ["#results", "Results"],
              ["#tokens", "Tokens"],
              ["#stack", "Stack"],
              ["#faq", "FAQ"],
            ].map(([h, t]) => (
              <a key={h} className="relative py-1 transition-colors hover:text-t1" href={h}>
                {t}
              </a>
            ))}
          </nav>
          <Button href={GH} hint="G">
            GitHub
          </Button>
        </div>
        <div aria-hidden className="progress absolute inset-x-0 -bottom-px h-[2px] bg-t1" />
      </header>

      <main>
        {/* ── hero ── */}
        <div className="hero-bg">
          <section className={`${COL} pt-8 md:pt-12`}>
            <Box stack="first">
              <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 px-4 py-2.5 text-[13px] text-t3">
                <span>
                  <b className="font-medium text-t1">{data.catalog.total}</b>-bug evaluation catalog
                </span>
                {reals.length > 0 && (
                  <>
                    <Dot />
                    <span>
                      <b className="font-medium text-t1">{reals.length}</b> real open-source bugs
                    </span>
                  </>
                )}
                <Dot />
                <span>
                  <b className="font-medium text-t1">{f.templates}</b> Clef decision templates
                </span>
                <Dot />
                <span>
                  <b className="font-medium text-t1">{f.mcpServers}</b> MCP servers · <b className="font-medium text-t1">{f.mcpTools}</b> tools
                </span>
                <Dot />
                <span>MIT licensed</span>
              </div>
            </Box>
            <Box stack="middle" className="overflow-hidden">
              <div className="grid items-center gap-10 px-6 py-14 sm:px-10 md:py-20 lg:grid-cols-[1.2fr_1fr] lg:gap-12">
                <div>
                  <div className="fx inline-flex items-center gap-2 border border-line bg-surface px-2.5 py-1 font-mono text-[11px] text-t3" style={v(0)}>
                    <span className="pulse inline-block h-1.5 w-1.5 rounded-full bg-good" />
                    open source · crash → pull request
                  </div>
                  <h1 className="fx mt-6 font-display text-[44px] font-medium leading-[0.98] tracking-[-0.04em] text-t1 sm:text-[60px] xl:text-[70px]" style={v(1)}>
                    <Mark>An autonomous</Mark>
                    <br />
                    on-call engineer.
                  </h1>
                  <p className="fx mt-7 max-w-[50ch] text-[16.5px] leading-[1.6] text-t3" style={v(2)}>
                    A crash, a rider&apos;s bug report or a labeled GitHub issue goes in. Triage, an evidence-backed root
                    cause, a mitigation, a test that fails on the shipped release, the fix and its proof come out — as a
                    pull request. Measured on a bug catalog and on real open-source bugs, with every number generated.
                  </p>
                  <div className="fx mt-8 flex flex-wrap gap-2" style={v(3)}>
                    <Button href="#start" variant="primary" hint="S">
                      Get started
                    </Button>
                    <Button href={doc("README.md")} hint="D">
                      Documentation
                    </Button>
                    <Button href="#results" hint="R">
                      See the results
                    </Button>
                  </div>
                </div>
                {run && (
                  <div className="fx fx-zoom" style={v(2)}>
                    <div className="parallax" data-scrub="1,0" style={{ ["--d" as string]: "-70px" }}>
                      <LiveRun run={run} model={data.model} />
                      <p className="mt-3 text-center font-mono text-[10.5px] text-t4">
                        replay of a real baseline run · {run.runId}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </Box>
            <Box stack="last" className="marquee">
              <div className="marquee-track">
                {[...STACK, ...STACK].map(([name, role], i) => (
                  <div key={i} className="flex min-w-[170px] flex-col items-center justify-center border-r border-line px-6 py-4">
                    <span className="font-display text-[15px] font-medium tracking-[-0.01em] text-t2">{name}</span>
                    <span className="mt-0.5 font-mono text-[9.5px] uppercase tracking-[0.05em] text-t4">{role}</span>
                  </div>
                ))}
              </div>
            </Box>
          </section>
        </div>

        {/* ── statement, lit word by word as you scroll ── */}
        <section className={`${COL} pt-[140px]`}>
          <div className="font-mono text-[11px] uppercase tracking-[0.06em] text-t3">The principle</div>
          <p
            data-scrub="0.9,0.5"
            className="mt-5 max-w-[22ch] font-display text-[34px] font-medium leading-[1.12] tracking-[-0.03em] text-t1 sm:text-[48px] md:text-[60px]"
            style={{ ["--n" as string]: STATEMENT.split(" ").length }}
          >
            {STATEMENT.split(" ").map((w, i) => (
              <span key={i} className="word" style={v(i)}>
                {w}{" "}
              </span>
            ))}
          </p>
        </section>

        {/* ── the loop, pinned while you scroll through its four phases ── */}
        <section id="how" className={`${COL} pt-[140px]`}>
          <H2>
            Investigate, fix, prove — <Mark>repeat.</Mark>
          </H2>
          <Lead className="mt-5">
            Four phases, twelve steps, always in this order. Clef makes each judgement call with a probability,
            LLM agents reason and write code, and deterministic code performs every write — behind a policy
            gate.
          </Lead>
          <div className="mt-10">
            <Loop />
          </div>
        </section>

        {/* ── architecture: four plates that pull apart as you scroll ── */}
        <section id="architecture" className={`${COL} pt-[140px]`}>
          <H2>
            One system, <Mark>four layers.</Mark>
          </H2>
          <Lead className="mt-5">
            Problems surface at the bottom and rise; agents only see the world through evidence tools; every action
            leaves through the top, behind a policy gate.
          </Lead>
          <div className="mt-10">
            <Architecture servers={f.mcpServers} tools={f.mcpTools} />
          </div>
        </section>

        {/* ── features ── */}
        <section id="features" className={`${COL} pt-[140px]`}>
          <H2 className="max-w-[18ch]">
            Everything an on-call engineer does, <Mark>with receipts.</Mark>
          </H2>
          <Lead className="mt-5">One pipeline from the first crash report to a merged fix, with evidence at every step.</Lead>
          <div className="mt-12">
            <Features />
          </div>
        </section>

        {/* ── results ── */}
        <section id="results" className={`${COL} pt-[140px]`}>
          <H2>
            <Mark>Measured</Mark>, not claimed.
          </H2>
          <Lead className="mt-5">
            {data.catalog.total} bugs injected into a small ride-hailing app as natural-looking release commits —{" "}
            {data.catalog.code} that need a code fix, {data.catalog.notOurs} where the right answer is to route it. The
            agent never sees the answer key; an evaluator scores its root cause and runs hidden tests on its fix. Built
            from{" "}
            <a className="text-t1 underline underline-offset-2" href={report}>
              evals/reports/{data.report}
            </a>
            .
          </Lead>
          <div className="mt-12">
            <Results data={data} />
          </div>
          <div className="mt-2 grid gap-2 md:grid-cols-2">
            <Box className="fx p-6">
              <div className="font-mono text-[11px] uppercase tracking-[0.04em] text-good">✓ What works</div>
              <ul className="mt-4 space-y-3 text-[14.5px] leading-[1.55] text-t2">
                <li>Crash-data bugs — locale and currency edge cases, a nil-map panic, a removed await, a battery-draining poller: ten code bugs pass every lane in all three seeds.</li>
                <li>Following a rider&apos;s report into the backend and moving the fix to the service that holds the defect — none of those bugs had the right root cause before the hand-off.</li>
                <li>Saying &ldquo;not our bug&rdquo; — a WebView crash, a vendored SDK, a misconfigured flag, intended behaviour — and routing it instead of patching, for about a cent a run.</li>
              </ul>
            </Box>
            <Box stripes className="fx p-6" >
              <div className="font-mono text-[11px] uppercase tracking-[0.04em] text-bad">✗ What doesn&apos;t, yet</div>
              <ul className="mt-4 space-y-3 text-[14.5px] leading-[1.55] text-t2">
                <li>Stopping where the symptom surfaced: a CORS change and a payments panic are blamed on the client and the gateway.</li>
                <li>Fixes narrower than the regression: they pass the agent&apos;s own test but not the hidden one.</li>
                <li>An active incident still loses to suspicious code, and seeds disagree on ten bugs: one run of a bug proves little.</li>
              </ul>
            </Box>
          </div>
          {replay.length > 0 && (
            <div id="clef" className="fx mt-2 cbox p-6">
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
                      <div key={l.label} className="bg-surface p-4">
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
            <div id="real" className="fx mt-2 cbox p-6">
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
              Where the <Mark>tokens</Mark> go.
            </H2>
            <Lead className="mt-5">
              Every agent turn re-sends the prompt, the tools and the history. A context audit split{" "}
              {(ctx.inputTokens / 1e6).toFixed(1)}M input tokens from real runs by what they carried — so we build the
              context-engineering technique the data points to, not the one that sounds best.
            </Lead>
            <div className="grow mt-12 cbox p-6">
              <div className="flex items-baseline justify-between font-mono text-[11px] uppercase tracking-[0.04em] text-t3">
                <span>Every input token, by what it carried</span>
                <span className="normal-case tracking-normal text-t4">{(ctx.inputTokens / 1e6).toFixed(1)}M tokens</span>
              </div>
              <div className="mb-6 mt-4 flex h-16 w-full gap-[3px]">
                {[
                  [ctx.toolsShare, "bg-mark", "tool results"],
                  [ctx.prefixShare, "stripes border border-line-strong", "fixed prefix"],
                  [ctx.modelShare, "bg-[#8b7cf0]", "model output"],
                ].map(([share, cls, label], i) => (
                  <div key={label as string} className="h-full min-w-0" style={{ flex: `${share as number} 1 0` }}>
                    <div className={`bar flex h-full items-end border border-line-strong p-2 ${cls}`} style={v(i * 3)}>
                      <span className="font-display text-[18px] font-medium tracking-[-0.02em] text-t1">{pct(share as number)}</span>
                    </div>
                    <div className="mt-2 truncate text-[12.5px] text-t3">{label}</div>
                  </div>
                ))}
              </div>
            </div>
            <div className="cbox no-top -mt-px grid gap-px bg-line md:grid-cols-[1fr_1.6fr]">
              <div className="bg-surface p-6">
                <div className="font-display text-[56px] font-medium leading-none tracking-[-0.04em]">
                  <span data-count>{pct(ctx.cacheShare)}</span>
                </div>
                <div className="mt-2 text-[13.5px] text-t3">of input served from the prompt cache — the fixed prefix and history are cheap; the volume isn&apos;t.</div>
              </div>
              <div className="grow bg-surface p-6">
                <div className="font-mono text-[11px] uppercase tracking-[0.04em] text-t3">Heaviest tools · share of all input</div>
                <div className="mt-4 space-y-3">
                  {ctx.topTools.map((t, i) => (
                    <div key={t.tool} className="flex items-center gap-3">
                      <span className="w-32 truncate font-mono text-[12px] text-t2">{t.tool}</span>
                      <div className="h-3 flex-1 border border-line bg-surface-1">
                        <div className="bar h-full bg-t1" style={{ width: pct(t.share / ctx.topTools[0].share), ...v(i) }} />
                      </div>
                      <span className="w-10 text-right font-mono text-[12px] text-t3">{pct(t.share)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            {before && ctxArms.length > 1 && <ArmCompare arms={ctxArms} report={report} />}
          </section>
        )}

        {/* ── stack ── */}
        <section id="stack" className={`${COL} pt-[140px]`}>
          <H2>
            Works with <Mark>your stack.</Mark>
          </H2>
          <Lead className="mt-5">
            Any OpenAI-compatible model, OpenTelemetry for telemetry, MCP for evidence. Every integration has a mock, so
            the whole pipeline runs without a single key.
          </Lead>
          <div className="mt-12">
            <Pills title={`Evidence · ${f.mcpServers} MCP servers · ${f.mcpTools} tools`} items={["crash analytics", "code search", "git history", "feature flags", "bug reports", "logging", "tracing", "metrics & profiles", "incidents", "releases", "Jira"]} stack="first" />
            <div className="-mt-px grid md:grid-cols-2">
              <Pills title="Models & decisions" items={["Cloudflare Clef", "OpenRouter", "GroqCloud", "OpenAI-compatible", "LangGraph", "LangChain"]} stack="middle" />
              <Pills title="Telemetry" items={["OpenTelemetry", "Jaeger", "Loki", "Prometheus", "Phoenix", "Langfuse"]} stack="middle" className="md:-ml-px" />
            </div>
            <Pills title="Target languages & tools" items={["TypeScript · React", "Python · FastAPI", "Go", "Playwright", "GitHub", "GitHub App", "Unleash", "Docker"]} stack="middle" />
            <Pills title="On the roadmap" items={["LiteLLM", "Ollama · vLLM", "Promptfoo", "Inspect AI", "GlitchTip", "SWE-bench Lite"]} stack="last" muted />
          </div>
        </section>

        {/* ── open ── */}
        <section id="open" className={`${COL} pt-[140px]`}>
          <H2>
            Open platform. <Mark>Open process.</Mark>
          </H2>
          <div className="mt-12 cbox">
            <div className="grid gap-px bg-line md:grid-cols-3">
              <Col i={0} title="Self-host it" items={[["make up — app, telemetry, sources", null], ["mock mode, no keys needed", null], ["The GitHub App on your repos", doc("docs/github-app.md")]]} />
              <Col i={1} title="Read the process" items={[["Lessons learned", doc("docs/LESSONS.md")], ["Architecture", doc("docs/ARCHITECTURE.md")], ["Decision records", `${GH}/tree/main/docs/adr`]]} />
              <Col i={2} title="Check the numbers" items={[["Latest report", report], ["Roadmap", doc("docs/ROADMAP.md")], ["Progress log", doc("docs/PROGRESS.md")]]} />
            </div>
          </div>
        </section>

        {/* ── get started: a dark band ── */}
        <section id="start" className="relative mt-[140px] overflow-hidden bg-code text-[#f3f1ea]">
          <div aria-hidden className="pointer-events-none absolute inset-0 opacity-[0.07] [background-image:linear-gradient(to_right,#fff_1px,transparent_1px),linear-gradient(to_bottom,#fff_1px,transparent_1px)] [background-size:28px_28px]" />
          <div className={`${COL} relative grid items-center gap-12 py-24 lg:grid-cols-[1fr_1.15fr]`}>
            <div>
              <div className="fx font-mono text-[11px] uppercase tracking-[0.06em] text-[#9a988f]">Get started</div>
              <h2 className="fx mt-4 font-display text-[40px] font-medium leading-[1] tracking-[-0.03em] sm:text-[56px]" style={v(1)}>
                <span className="text-mark">Try it</span> in a few minutes.
              </h2>
              <p className="fx mt-5 max-w-[42ch] text-[16px] leading-[1.6] text-[#bdbbb2]" style={v(2)}>
                The keyless demo runs the whole pipeline with a scripted model and mocked integrations — no API keys, no
                accounts.
              </p>
              <div className="fx mt-8 flex flex-wrap gap-2" style={v(3)}>
                <a href={GH} className="inline-flex h-9 items-center gap-2 border border-mark bg-mark px-4 text-[13px] font-medium text-t1 transition-transform hover:-translate-y-px">
                  Star on GitHub
                  <kbd className="grid h-[18px] min-w-[18px] place-items-center border border-black/20 bg-black/10 px-1 font-mono text-[10px]">G</kbd>
                </a>
                <a href={`${GH}#-quickstart`} className="inline-flex h-9 items-center border border-white/25 px-4 text-[13px] text-[#f3f1ea] transition-colors hover:border-white/60">
                  Quickstart →
                </a>
              </div>
            </div>
            <div className="typed fx fx-zoom border border-white/15 bg-[#232321] shadow-[0_40px_80px_-30px_rgba(0,0,0,0.6)]" style={v(2)}>
              <div className="flex items-center gap-1.5 border-b border-white/10 px-4 py-3">
                <span className="h-2.5 w-2.5 rounded-full bg-[#5a5953]" />
                <span className="h-2.5 w-2.5 rounded-full bg-[#5a5953]" />
                <span className="h-2.5 w-2.5 rounded-full bg-[#5a5953]" />
                <span className="ml-3 font-mono text-[11px] text-[#8a887f]">~/DebugAssist</span>
              </div>
              <div className="overflow-x-auto p-5 font-mono text-[12.5px] leading-[1.9]">
                {TERMINAL.map(([cmd, note], i) => (
                  <div key={cmd} className="type-line whitespace-nowrap" style={v(i)}>
                    <span className="text-mark">$</span> {cmd}
                    {note && <span className="text-[#8a887f]">  # {note}</span>}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* ── FAQ ── */}
        <section id="faq" className={`${COL} pt-[140px]`}>
          <div className="grid gap-10 md:grid-cols-[1fr_1.7fr]">
            <H2>Questions &amp; answers</H2>
            <div className="border-t border-dashed border-line-dash">
              {FAQ.map(([q, a], i) => (
                <details key={q} className="fx group border-b border-dashed border-line-dash" style={v(i)}>
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-4 py-5 text-[16px] font-medium text-t1 transition-colors hover:text-t2">
                    {q}
                    <span className="grid h-6 w-6 shrink-0 place-items-center border border-line font-mono text-t3 transition-transform duration-300 group-open:rotate-45">+</span>
                  </summary>
                  <p className="max-w-[64ch] pb-5 text-[14.5px] leading-[1.65] text-t3">{a}</p>
                </details>
              ))}
            </div>
          </div>
        </section>
      </main>

      <footer className="mt-[140px] overflow-hidden border-t border-line">
        <div className={`${COL} grid gap-8 py-12 text-[12.5px] sm:grid-cols-4`}>
          <div className="sm:col-span-1">
            <div className="flex items-center gap-2 font-display text-[14px] font-semibold">
              <span className="grid h-4 w-4 place-items-center border border-t1 bg-mark font-mono text-[9px]">D</span>
              DebugAssist
            </div>
            <p className="mt-2 text-t3">MIT licensed, independent open-source project.</p>
          </div>
          <FooterCol title="Project" links={[["GitHub", GH], ["README", doc("README.md")], ["Latest report", report]]} />
          <FooterCol title="Docs" links={[["Lessons learned", doc("docs/LESSONS.md")], ["Roadmap", doc("docs/ROADMAP.md")], ["MCP servers", doc("docs/mcp.md")]]} />
          <FooterCol title="Process" links={[["Architecture", doc("docs/ARCHITECTURE.md")], ["Decisions", `${GH}/tree/main/docs/adr`], ["Progress", doc("docs/PROGRESS.md")]]} />
        </div>
        <div className="border-t border-line">
          <div className={`${COL} py-4 text-[11.5px] text-t4`}>
            Not affiliated with Uber, Cloudflare, OpenAI, OpenRouter, Groq or any company named here; names indicate
            integrations only.
          </div>
        </div>
        {/* the wordmark rises out of the page edge as you reach the bottom */}
        <div aria-hidden className="h-[13vw] max-h-[190px] select-none overflow-hidden" data-scrub="1,1">
          <div className="rise">
            <div className="wordmark mx-auto w-max pt-[1vw] font-display font-semibold tracking-[-0.05em]">DebugAssist</div>
          </div>
        </div>
      </footer>
    </>
  );
}

const kTok = (n: number) => (n < 20_000 ? `${(n / 1000).toFixed(1)}K` : `${Math.round(n / 1000)}K`);

const ARM_STYLE: Record<string, { cls: string; what: string }> = {
  "fix-quality": { cls: "bg-line-strong", what: "the code every experiment re-ran" },
  lean: { cls: "bg-mark border border-line-strong", what: "file reads capped at 120 lines, an outline tool, long logs offloaded" },
  clear: { cls: "bg-[#8b7cf0] border border-line-strong", what: "old tool results replaced by one-line stubs, in batches" },
  compact: { cls: "bg-[#e0901b] border border-line-strong", what: "old steps folded into working notes by the model" },
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
    <div className="cbox no-top -mt-px grid md:grid-cols-[1fr_1.6fr]">
      <div className="stripes border-b border-line p-6 md:border-b-0 md:border-r">
        <div className="font-mono text-[11px] uppercase tracking-[0.04em] text-t3">Measured · {n} context experiments</div>
        <div className="fx mt-2 font-display text-[24px] font-medium leading-tight tracking-[-0.02em]">
          Fewer tokens <Mark>isn&apos;t</Mark> cheaper.
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
              <span className={`mt-[5px] inline-block h-2.5 w-2.5 shrink-0 ${ARM_STYLE[a.arm]?.cls ?? "bg-line"}`} />
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
                  <div className="h-3 flex-1 bg-surface-1">
                    <div
                      className={`bar h-full ${ARM_STYLE[a.arm]?.cls ?? "bg-line"}`}
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

const STATEMENT =
  "The plan is code, not a prompt. Models never choose the next step. Clef makes every judgement call with a probability, agents reason and write the code, and deterministic code performs every write.";

const STACK: [string, string][] = [
  ["Vitals", "crash analytics"],
  ["BugDrop", "bug reports"],
  ["Clef", "decisions"],
  ["LangGraph", "fixed plan"],
  ["MCP", "evidence"],
  ["OpenTelemetry", "telemetry"],
  ["Jaeger", "traces"],
  ["Loki", "logs"],
  ["Prometheus", "metrics"],
  ["Unleash", "flags"],
  ["GitHub", "pull requests"],
  ["Jira", "tickets"],
  ["Docker", "sandbox"],
  ["Playwright", "simulated riders"],
];

const TERMINAL: [string, string][] = [
  [`git clone --recurse-submodules ${GH}`, ""],
  ["make bootstrap && make up && make flags", ""],
  ["make demo-push-crash", "keyless: scripted LLM, mocks"],
  ["make dashboard", "http://localhost:3000"],
];

const FAQ: [string, string][] = [
  ["What is DebugAssist?", "An open-source pipeline that does what an on-call engineer does when something breaks: it notices the crash or the rider's report, triages it, finds the root cause with evidence, proposes a mitigation, writes a test that fails on the shipped release, fixes the code, proves the fix and opens a pull request — or says it isn't our bug and routes it."],
  ["Does an LLM decide what happens next?", "No. The plan is a fixed graph in code. LLM agents reason and write code inside steps; every judgement call is a Clef decision with a probability, mapped to act, escalate or a safe default by policy; deterministic code performs every write."],
  ["Can it change production on its own?", "No. Writes go through a policy gate and an audit log. It pushes only to debugassist/* bot branches — of the demo repositories, and of repositories the GitHub App is installed on — opens pull requests as drafts there, never touches the default branch, release branches or tags, needs approval for flag rollbacks, and is dry-run for anything the policy does not list."],
  ["Can I run it on my own repository?", "Yes, through the GitHub App: install it on the repository, add a .DebugAssist/pipeline.yaml saying how to install and test it, and label an issue debugassist. It checks out the default branch, investigates in a network-less sandbox, comments the root cause on the issue and, when a fix validates, opens a draft pull request. It is built and tested against a fake GitHub API and a mock; it has not yet run on a live repository."],
  ["How does it know which commit broke something?", "The root-cause step names a suspect by reading history. With the bisect proof on, the validated reproduction test is also run back through earlier releases until it passes, then git bisect finds the first commit where it fails — a result anyone can re-run. On python-semver#484 it found the change the reporter blamed, where the reading had named a later one."],
  ["How are the results measured?", "Each catalog bug is injected as a natural-looking commit, triggered by simulated riders, and discovered by the crash and bug-report sources. The agent's root cause is scored against an answer key it never sees, and hidden tests run on its fix. Every number on this page is read from the generated reports when the site is built."],
  ["Which models does it use?", "Any OpenAI-compatible API. The evaluation on this page ran on openai/gpt-6-luna through OpenRouter; decisions run on Cloudflare Clef."],
  ["Is it affiliated with Uber, Cloudflare or anyone named here?", "No. It is an independent project inspired by a public talk on MCP-powered crash investigation. Vitals and BugDrop are its own stand-ins for crash analytics and in-app bug reports."],
];

function Pills({ title, items, muted, stack, className = "" }: { title: string; items: string[]; muted?: boolean; stack?: "first" | "middle" | "last"; className?: string }) {
  return (
    <Box stack={stack} stripes={muted} className={`p-6 ${className}`}>
      <div className="font-mono text-[11px] uppercase tracking-[0.04em] text-t3">{title}</div>
      <div className="mt-4 flex flex-wrap gap-1.5">
        {items.map((i, k) => (
          <span
            key={i}
            className={`fx inline-flex h-8 items-center border px-3 text-[13px] transition-colors ${muted ? "border-dashed border-line-dash bg-surface text-t3" : "border-line bg-surface text-t2 hover:border-line-strong hover:bg-mark/40"}`}
            style={{ ["--i" as string]: k * 0.5 }}
          >
            {i}
          </span>
        ))}
      </div>
    </Box>
  );
}

function Col({ title, items, i }: { title: string; items: [string, string | null][]; i: number }) {
  return (
    <div className="spot fx bg-surface p-6" style={{ ["--i" as string]: i }}>
      <div className="font-mono text-[10.5px] text-t4">{String(i + 1).padStart(2, "0")}</div>
      <div className="mt-2 font-display text-[20px] font-medium tracking-[-0.015em]">{title}</div>
      <ul className="mt-3 space-y-2 text-[13.5px] text-t3">
        {items.map(([t, href]) => (
          <li key={t} className="flex items-center gap-2">
            <span className="inline-block h-[3px] w-[3px] bg-t3" />
            {href ? (
              <a className="underline decoration-line-dash underline-offset-2 hover:text-t1" href={href}>
                {t}
              </a>
            ) : (
              t
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function FooterCol({ title, links }: { title: string; links: [string, string][] }) {
  return (
    <div>
      <div className="font-mono text-[10.5px] uppercase tracking-[0.05em] text-t4">{title}</div>
      <ul className="mt-2 space-y-1.5">
        {links.map(([t, h]) => (
          <li key={t}>
            <a className="text-t3 hover:text-t1" href={h}>
              {t}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
