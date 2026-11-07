import Link from "next/link";
import { Banner, COL, SiteFooter, SiteHeader } from "@/components/Chrome";
import { Motion, Shortcuts } from "@/components/client";
import { HeroDiagram, Principle } from "@/components/Diagrams";
import { CHAPTERS, Figure } from "@/components/Page";
import { Results } from "@/components/Results";
import { Button, Eyebrow, GH, H2, Lead, doc } from "@/components/ui";
import { bisectReplay, facts, featuredRun, realBugs, results } from "@/lib/data";

const base = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const v = (i: number) => ({ ["--i" as string]: i });

export default function Home() {
  const data = results();
  const reals = realBugs();
  const bis = bisectReplay();
  const foundBisect = bis.find((b) => b.found > 0);
  const f = facts();
  const run = featuredRun(data);
  const report = doc(`evals/reports/${data.report}/report.md`);

  return (
    <>
      <Motion />
      <Shortcuts map={{ g: GH, d: doc("README.md"), r: `${base}/results/`, s: "#start" }} />
      <SiteHeader
        banner={
          foundBisect && (
            <Banner href="/results/#real" tag="culprit commit, proven">
              {foundBisect.issue.replace("https://github.com/", "").replace("/issues/", "#")} bisects to{" "}
              {foundBisect.commit.slice(0, 7)} in {foundBisect.found}/{foundBisect.tests} runs, by running the agent&apos;s own test
            </Banner>
          )
        }
      />

      <main>
        {/* ── hero: a framed plate between hatched margins ── */}
        <section className="relative">
          <div aria-hidden className="hatch absolute inset-y-0 left-0 hidden w-[calc((100vw-1240px)/2+32px)] xl:block" />
          <div aria-hidden className="hatch absolute inset-y-0 right-0 hidden w-[calc((100vw-1240px)/2+32px)] xl:block" />
          <div className={`${COL} relative pt-10 md:pt-14`}>
            <div className="cbox bg-surface">
              <dl className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 border-b border-line px-4 py-3.5 text-[14px] text-t2 sm:text-[15px]">
                {[
                  [String(data.catalog.total), "-bug evaluation catalog"],
                  [String(reals.length), " real open-source bugs"],
                  [String(f.templates), " Clef decision templates"],
                  [String(f.mcpServers), ` MCP servers · ${f.mcpTools} tools`],
                ].map(([n, l], i) => (
                  <div key={l} className="flex items-center gap-6">
                    {i > 0 && <span aria-hidden className="hidden text-t4 sm:inline">·</span>}
                    <div>
                      <dt className="sr-only">{l.trim()}</dt>
                      <dd>
                        <span className="font-semibold text-t1">{n}</span>
                        {l}
                      </dd>
                    </div>
                  </div>
                ))}
              </dl>
              <div className="px-5 py-16 text-center sm:px-10 md:py-24">
                <h1 className="fx display mx-auto max-w-[14ch] text-[48px] leading-[1.06] text-t1 sm:text-[72px] lg:text-[92px]" style={v(1)}>
                  <span className="hl">The on-call engineer</span> <span className="hl">that shows its work.</span>
                </h1>
                <p className="fx mx-auto mt-10 max-w-[62ch] text-[17px] leading-[1.65] text-t2 sm:text-[18.5px]" style={v(2)}>
                  A crash, a rider&apos;s report or a labeled GitHub issue goes in. A root cause backed by evidence, a
                  test that fails on the shipped release, the fix and its proof come out — as a pull request. Every
                  number on this page is generated from the evaluation reports.
                </p>
                <div className="fx mt-10 flex flex-wrap justify-center gap-3" style={v(3)}>
                  <Button href="#start" variant="primary" hint="S">
                    Get started
                  </Button>
                  <Button href={doc("README.md")} hint="D">
                    Documentation
                  </Button>
                  <Button href={`${base}/results/`} hint="R">
                    See the results
                  </Button>
                </div>
              </div>
            </div>

            {run && (
              <div className="mt-12">
                <Figure n="1" title="what goes in, what comes out" note={`${run.issue}, an evaluated run`}>
                  <HeroDiagram run={run} servers={f.mcpServers} tools={f.mcpTools} templates={f.templates} />
                </Figure>
              </div>
            )}
          </div>
        </section>

        {/* ── the principle ── */}
        <section className={`${COL} pt-[150px]`}>
          <Eyebrow n="01">The principle</Eyebrow>
          <H2 className="mt-5 max-w-[20ch]">
            The plan is code. <span className="hl">Models never choose the next step.</span>
          </H2>
          <Lead className="mt-6">
            Three actors, each doing only what it is good at. Clef turns every judgement call into a probability, the
            LLM reasons and writes code inside a step, and deterministic code performs every write.
          </Lead>
          <div className="mt-12">
            <Principle templates={f.templates} />
          </div>
        </section>

        {/* ── contents: one page per chapter ── */}
        <section id="contents" className={`${COL} scroll-mt-24 pt-[150px]`}>
          <Eyebrow n="02">Contents</Eyebrow>
          <H2 className="mt-5 max-w-[18ch]">
            Read it like a <span className="hl">design doc.</span>
          </H2>
          <Lead className="mt-6">
            Each part of the system has its own page. Most are rendered from the files that define them — the decision
            templates, the write policy, the server table, the threat model and the design records — so they cannot drift
            from the code.
          </Lead>
          <ol className="mt-12 border-t border-line-strong">
            {CHAPTERS.map((c, i) => (
              <li key={c.href} className="fx" style={v(i * 0.4)}>
                <Link
                  href={c.href}
                  className="group grid gap-x-8 gap-y-1 border-b border-line py-7 transition-colors hover:bg-sunk/40 md:grid-cols-[80px_minmax(0,300px)_minmax(0,1fr)_24px] md:items-baseline"
                >
                  <span className="font-mono text-[12px] text-t3">{c.n}</span>
                  <span className="text-[26px] font-medium tracking-[-0.02em] text-t1 sm:text-[30px]">{c.title}</span>
                  <span className="max-w-[60ch] text-[15px] leading-[1.6] text-t3">{c.blurb}</span>
                  <span className="hidden font-mono text-[18px] text-t3 transition-transform group-hover:translate-x-1 group-hover:text-t1 md:block">→</span>
                </Link>
              </li>
            ))}
          </ol>
        </section>

        {/* ── results ── */}
        <section id="results" className={`${COL} scroll-mt-24 pt-[150px]`}>
          <Eyebrow n="03">Results</Eyebrow>
          <H2 className="mt-5">
            Measured, <span className="hl">not claimed.</span>
          </H2>
          <Lead className="mt-6">
            {data.catalog.total} bugs injected into a small ride-hailing app as natural-looking release commits. The agent
            never sees the answer key; an evaluator scores its root cause and runs hidden tests on its fix. Built from{" "}
            <a className="text-t1 underline decoration-line-2 underline-offset-4 hover:decoration-t1" href={report}>
              evals/reports/{data.report}
            </a>
            .
          </Lead>
          <div className="mt-12">
            <Results data={data} compact />
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <div className="fx panel p-7">
              <div className="label text-t1">
                What works
              </div>
              <ul className="mt-5 space-y-4 text-[15px] leading-[1.6] text-t2">
                <li>Crash-data bugs — locale and currency edge cases, a nil-map panic, a removed await, a battery-draining poller: ten code bugs pass every lane in all three seeds.</li>
                <li>Following a rider&apos;s report into the backend and moving the fix to the service that holds the defect.</li>
                <li>Saying &ldquo;not our bug&rdquo; — a WebView crash, a vendored SDK, a misconfigured flag — and routing it instead of patching, for about a cent a run.</li>
              </ul>
            </div>
            <div className="fx panel p-7" style={v(1)}>
              <div className="label text-t3">
                What doesn&apos;t, yet
              </div>
              <ul className="caveat mt-5 space-y-4 text-[17px] text-t2">
                <li>Stopping where the symptom surfaced: a CORS change and a payments panic are blamed on the client and the gateway.</li>
                <li>Fixes narrower than the regression: they pass the agent&apos;s own test but not the hidden one.</li>
                <li>An active incident still loses to suspicious code, and seeds disagree on ten bugs: one run of a bug proves little.</li>
              </ul>
            </div>
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-3">
            {[
              ["/clef/#reach", "Does Clef help?", "Not measured yet: every recorded decision was answered by the LLM fallback."],
              ["/results/#real", "Real open-source bugs", `${reals.length} public issues, each run on the code it was filed against, with bisect proofs.`],
              ["/results/#tokens", "Where the tokens go", "A context audit of real runs, and three context-engineering experiments."],
            ].map(([href, t, b], i) => (
              <Link key={href} href={href} className="fx panel group flex flex-col justify-between gap-8 p-7 transition-[border-color,transform] hover:-translate-y-0.5 hover:border-line-strong" style={v(i)}>
                <div>
                  <h3 className="title text-[22px] text-t1">{t}</h3>
                  <p className="mt-2 text-[14.5px] leading-[1.6] text-t2">{b}</p>
                </div>
                <span className="font-mono text-[12px] text-t1">
                  Lab notebook <span className="inline-block transition-transform group-hover:translate-x-1">→</span>
                </span>
              </Link>
            ))}
          </div>
        </section>

        {/* ── get started ── */}
        <section id="start" className={`${COL} scroll-mt-24 pt-[150px]`}>
  <div className="relative overflow-hidden  bg-term text-term-fg">
            <div className="relative grid items-center gap-12 p-8 sm:p-12 lg:grid-cols-[1fr_1.15fr] lg:p-16">
              <div>
                <div className="fx label text-term-dim">Get started</div>
                <h2 className="fx title mt-5 text-[40px] sm:text-[56px]" style={v(1)}>
                  Try it in a few minutes.
                </h2>
                <p className="fx mt-5 max-w-[42ch] text-[16.5px] leading-[1.65] text-term-dim" style={v(2)}>
                  The keyless demo runs the whole pipeline with a scripted model and mocked integrations — no API keys,
                  no accounts.
                </p>
                <div className="fx mt-8 flex flex-wrap gap-3" style={v(3)}>
  <a href={GH} className="inline-flex h-10 items-center gap-2.5 bg-amber-fill px-4 text-[14px] font-medium text-ink transition-transform active:scale-[0.98]">
                    Star on GitHub
                  </a>
  <a href={`${GH}#-quickstart`} className="inline-flex h-10 items-center border border-term-line px-4 text-[14px] font-medium text-term-fg transition-colors hover:border-term-dim">
                    Quickstart →
                  </a>
                </div>
              </div>
  <div className="typed fx overflow-hidden  border border-term-line bg-term-panel " style={v(2)}>
                <div className="flex items-center gap-2 border-b border-term-line px-4 py-3">
                  <span className="font-mono text-[11px] text-term-dim">~/DebugAssist</span>
                </div>
                <div className="overflow-x-auto p-5 font-mono text-[12.5px] leading-[1.95]">
                  {TERMINAL.map(([cmd, note], i) => (
                    <div key={cmd} className="type-line whitespace-nowrap" style={v(i)}>
                      <span className="text-amber-fill">$</span> {cmd}
                      {note && <span className="text-term-dim">  # {note}</span>}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── FAQ ── */}
        <section id="faq" className={`${COL} scroll-mt-24 pt-[150px]`}>
          <div className="grid gap-10 md:grid-cols-[1fr_1.7fr]">
            <div>
              <Eyebrow n="04">FAQ</Eyebrow>
              <H2 className="mt-5">
                Questions &amp; answers
              </H2>
              <p className="mt-6 text-[15px] leading-[1.6] text-t3">
                Something else?{" "}
                <a className="text-t1 underline decoration-line-2 underline-offset-4" href={`${GH}/issues`}>
                  Open an issue
                </a>
                , or read the{" "}
                <a className="text-t1 underline decoration-line-2 underline-offset-4" href={`${base}/results/`}>
                  lab notebook
                </a>
                .
              </p>
            </div>
            <div className="border-t border-line">
              {FAQ.map(([q, a], i) => (
                <details key={q} className="fx group border-b border-line" style={v(i * 0.5)}>
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-4 py-5 text-[17px] font-medium tracking-[-0.01em] text-t1 transition-colors hover:text-t2">
                    {q}
  <span className="grid h-7 w-7 shrink-0 place-items-center  border border-line font-mono text-t3 transition-transform duration-300 group-open:rotate-45">+</span>
                  </summary>
                  <p className="max-w-[64ch] pb-6 text-[15px] leading-[1.7] text-t2">{a}</p>
                </details>
              ))}
            </div>
          </div>
        </section>
      </main>
      <SiteFooter report={report} />
    </>
  );
}

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
  ["Would a plain agent do as well?", "That is what the baseline arm is for: one tool-using agent on the same issue, the same release worktree and the same evidence and code tools, with the root cause's and the fix's limits combined — and none of the plan: no evidence bundle, decisions, reproduction contract or validation. It is graded by the same scorer and hidden tests. It is built and tested offline; it has not been run on the catalog yet, so there is no comparison to show."],
  ["Which models does it use?", "Any OpenAI-compatible API. The evaluation on this page ran on openai/gpt-6-luna through OpenRouter; decisions run on Cloudflare Clef."],
  ["Is it affiliated with Uber, Cloudflare or anyone named here?", "No. It is an independent project inspired by a public talk on MCP-powered crash investigation. Vitals and BugDrop are its own stand-ins for crash analytics and in-app bug reports."],
];
