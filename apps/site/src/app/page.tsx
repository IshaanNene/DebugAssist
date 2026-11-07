import Link from "next/link";
import { Motion, Shortcuts } from "@/components/client";
import { Banner, COL, SiteFooter, SiteHeader } from "@/components/Chrome";
import { Features } from "@/components/Features";
import { Receipt } from "@/components/Receipt";
import { Results } from "@/components/Results";
import { RunConsole } from "@/components/RunConsole";
import { Actors, Layers, Pipeline, Safety } from "@/components/Sections";
import { Button, GH, H2, Lead, Panel, doc } from "@/components/ui";
import { bisectReplay, deciderReplay, facts, featuredRun, realBugs, results, runTimings, writePolicy } from "@/lib/data";

const base = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export default function Home() {
  const data = results();
  const reals = realBugs();
  const replay = deciderReplay();
  const bis = bisectReplay();
  const foundBisect = bis.find((b) => b.found > 0);
  const f = facts();
  const run = featuredRun(data);
  const timings = run ? runTimings(run.runId) : null;
  const policy = writePolicy();
  const report = doc(`evals/reports/${data.report}/report.md`);
  const v = (i: number) => ({ ["--i" as string]: i });

  return (
    <>
      <Motion />
      <Shortcuts map={{ g: GH, d: doc("README.md"), r: "#results", s: "#start" }} />
      <SiteHeader
        banner={
          foundBisect && (
            <Banner href="/results/#real" tag="culprit commit, proven">
              {foundBisect.issue.replace("https://github.com/", "").replace("/issues/", "#")} bisects to{" "}
              {foundBisect.commit.slice(0, 7)} in {foundBisect.found}/{foundBisect.tests} runs, by running the agent&apos;s test
            </Banner>
          )
        }
      />

      <main>
        {/* ── hero: one real run, replayed ── */}
        <section className="hero-field overflow-hidden">
          <div className={`${COL} pt-12 md:pt-16`}>
            <div className="fx inline-flex items-center gap-2 rounded-full border border-line bg-raised/80 px-3 py-1 font-mono text-[11px] text-t2" style={v(0)}>
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-good" />
              open source · crash → pull request
            </div>
            <h1 className="fx display mt-7 text-[56px] text-t1 sm:text-[88px] xl:text-[120px]" style={v(1)}>
              On call, <span className="text-t3">with</span> receipts.
            </h1>
            <div className="fx mt-8 flex flex-wrap items-end justify-between gap-x-10 gap-y-6" style={v(2)}>
              <p className="max-w-[52ch] text-[17.5px] leading-[1.6] text-t2">
                A crash, a rider&apos;s report or a labeled GitHub issue goes in. A root cause backed by evidence, a failing
                test, the fix and its proof come out as a pull request.
              </p>
              <div className="flex flex-wrap gap-2">
                <Button href="#start" variant="primary" hint="S">
                  Get started
                </Button>
                <Button href="#results" hint="R">
                  See the results
                </Button>
                <Button href={doc("README.md")} hint="D">
                  Docs
                </Button>
              </div>
            </div>

            {run && timings && (
              <div className="fx mt-12 md:mt-14" style={v(3)}>
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
                        <Receipt source={{ file: `evals/reports/${data.report}/results.csv`, row: `run_id ${run.runId}`, field: "claims · claims_unsupported", raw: `${run.claims} · ${run.unsupported}` }}>
                          {run.claims} claims, {run.unsupported} unsupported
                        </Receipt>
                        .
                      </>
                    ),
                    fix: <>A {run.tier} test fails on the shipped release; the fix makes it pass.</>,
                    validate: (
                      <>
                        Suite green. Hidden test <span className="text-good">passed</span>:{" "}
                        <span className="font-mono text-[12px]">{run.hiddenTest.split("/").pop()}</span>.
                      </>
                    ),
                  }}
                />
                <p className="mt-4 text-center font-mono text-[11px] text-t3">
                  A real baseline run, replayed on its own clock. Tap any underlined figure for its source.
                </p>
              </div>
            )}

            <dl className="mt-16 grid grid-cols-2 gap-px overflow-hidden rounded-[8px] border border-line bg-line md:mt-20 md:grid-cols-4">
              {[
                [String(data.catalog.total), "bugs in the evaluation catalog"],
                [String(reals.length), "real open-source bugs"],
                [String(f.templates), "Clef decision templates"],
                [`${f.mcpServers} · ${f.mcpTools}`, "MCP servers · tools"],
              ].map(([n, l]) => (
                <div key={l} className="bg-surface px-5 py-6">
                  <dt className="sr-only">{l}</dt>
                  <dd className="font-mono text-[34px] font-medium leading-none tracking-[-0.03em] text-t1">{n}</dd>
                  <dd className="mt-2 text-[13px] text-t3">{l}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        {/* ── the three actors ── */}
        <section className={`${COL} pt-[140px]`}>
          <div className="label text-t3">The principle</div>
          <H2 className="mt-4 max-w-[18ch]">The plan is code. Models never choose the next step.</H2>
          <div className="mt-12">
            <Actors templates={f.templates} />
          </div>
        </section>

        {/* ── how it works: the fixed plan ── */}
        <section id="how" className={`${COL} scroll-mt-20 pt-[140px]`}>
          <div className="label text-t3">How it works</div>
          <H2 className="mt-4">Investigate, fix, prove — in that order.</H2>
          <Lead className="mt-5">
            Four phases, twelve steps, always the same sequence. Clef takes each judgement call, agents do the reasoning
            inside a step, and deterministic code performs every write.
          </Lead>
          <div className="mt-12">
            <Pipeline />
          </div>
        </section>

        {/* ── architecture: four layers ── */}
        <section id="architecture" className={`${COL} scroll-mt-20 pt-[140px]`}>
          <div className="label text-t3">Architecture</div>
          <H2 className="mt-4">One system, four layers.</H2>
          <Lead className="mt-5">
            Problems surface at the bottom and rise. Agents see the world only through evidence tools. Every action
            leaves through the top, behind a policy gate.
          </Lead>
          <div className="mt-12">
            <Layers servers={f.mcpServers} tools={f.mcpTools} />
          </div>
        </section>

        {/* ── features ── */}
        <section id="features" className={`${COL} scroll-mt-20 pt-[140px]`}>
          <div className="label text-t3">What it does</div>
          <H2 className="mt-4 max-w-[20ch]">Everything an on-call engineer does, with receipts.</H2>
          <div className="mt-12">
            <Features />
          </div>
        </section>

        {/* ── results: the headline, then the notebook ── */}
        <section id="results" className={`${COL} scroll-mt-20 pt-[140px]`}>
          <div className="label text-t3">Results</div>
          <H2 className="mt-4">Measured, not claimed.</H2>
          <Lead className="mt-5">
            {data.catalog.total} bugs injected into a small ride-hailing app as natural-looking release commits. The agent
            never sees the answer key; an evaluator scores its root cause and runs hidden tests on its fix. Built from{" "}
            <a className="text-t1 underline underline-offset-2" href={report}>
              evals/reports/{data.report}
            </a>
            .
          </Lead>
          <div className="mt-12">
            <Results data={data} compact />
          </div>
          <div className="mt-2 grid gap-2 md:grid-cols-2">
            <Panel className="fx p-6">
              <div className="label text-good">✓ What works</div>
              <ul className="mt-4 space-y-3 text-[14.5px] leading-[1.55] text-t2">
                <li>Crash-data bugs — locale and currency edge cases, a nil-map panic, a removed await, a battery-draining poller: ten code bugs pass every lane in all three seeds.</li>
                <li>Following a rider&apos;s report into the backend and moving the fix to the service that holds the defect.</li>
                <li>Saying &ldquo;not our bug&rdquo; — a WebView crash, a vendored SDK, a misconfigured flag — and routing it instead of patching, for about a cent a run.</li>
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
          <div className="mt-2 grid gap-2 md:grid-cols-3">
            {[
              ["/results/#clef", "Does Clef help?", replay.length > 0 ? "Not yet: every logged decision replayed with Clef, an LLM and simple rules." : "Decision replay against the catalog."],
              ["/results/#real", "Real open-source bugs", `${reals.length} public issues, each run on the code it was filed against, with bisect proofs.`],
              ["/results/#tokens", "Where the tokens go", "A context audit of real runs, and three context-engineering experiments."],
            ].map(([href, t, b]) => (
              <Link key={href} href={href} className="fx panel group flex flex-col justify-between gap-6 p-6 transition-colors hover:border-line-strong">
                <div>
                  <h3 className="title text-[20px] text-t1">{t}</h3>
                  <p className="mt-2 text-[14px] leading-[1.55] text-t2">{b}</p>
                </div>
                <span className="font-mono text-[12px] text-amber">
                  Lab notebook <span className="inline-block transition-transform group-hover:translate-x-1">→</span>
                </span>
              </Link>
            ))}
          </div>
        </section>

        {/* ── safety: the real policy file ── */}
        <section id="safety" className={`${COL} scroll-mt-20 pt-[140px]`}>
          <div className="label text-t3">Safety</div>
          <H2 className="mt-4 max-w-[20ch]">It can&apos;t change production on its own.</H2>
          <Lead className="mt-5">
            Every side effect is listed in one policy file, and this section is rendered from it at build time — so the
            page can never drift from the rules the agent runs under.
          </Lead>
          <div className="mt-12">
            <Safety rules={policy.rules} branchPrefix={policy.branchPrefix} />
          </div>
        </section>

        {/* ── stack ── */}
        <section id="stack" className={`${COL} scroll-mt-20 pt-[140px]`}>
          <div className="label text-t3">Integrations</div>
          <H2 className="mt-4">Works with your stack.</H2>
          <Lead className="mt-5">
            Any OpenAI-compatible model, OpenTelemetry for telemetry, MCP for evidence. Every integration has a mock, so
            the whole pipeline runs without a single key.
          </Lead>
          <div className="mt-12">
            <div className="grid gap-2">
              <Pills title={`Evidence · ${f.mcpServers} MCP servers · ${f.mcpTools} tools`} items={["crash analytics", "code search", "git history", "feature flags", "bug reports", "logging", "tracing", "metrics & profiles", "incidents", "releases", "Jira"]} />
              <div className="grid gap-2 md:grid-cols-2">
                <Pills title="Models & decisions" items={["Cloudflare Clef", "OpenRouter", "GroqCloud", "OpenAI-compatible", "LangGraph", "LangChain"]} />
                <Pills title="Telemetry" items={["OpenTelemetry", "Jaeger", "Loki", "Prometheus", "Phoenix", "Langfuse"]} />
              </div>
              <Pills title="Target languages & tools" items={["TypeScript · React", "Python · FastAPI", "Go", "Playwright", "GitHub", "GitHub App", "Unleash", "Docker"]} />
              <Pills title="On the roadmap" items={["LiteLLM", "Ollama · vLLM", "Promptfoo", "Inspect AI", "GlitchTip", "SWE-bench Lite"]} muted />
            </div>
          </div>
        </section>

        {/* ── open ── */}
        <section id="open" className={`${COL} pt-[120px]`}>
          <div className="label text-t3">Open source</div>
          <H2 className="mt-4">Open platform. Open process.</H2>
          <div className="panel mt-12 overflow-hidden">
            <div className="grid gap-px bg-line md:grid-cols-3">
              <Col i={0} title="Self-host it" items={[["make up — app, telemetry, sources", null], ["mock mode, no keys needed", null], ["The GitHub App on your repos", doc("docs/github-app.md")]]} />
              <Col i={1} title="Read the process" items={[["Lessons learned", doc("docs/LESSONS.md")], ["Architecture", doc("docs/ARCHITECTURE.md")], ["Decision records", `${GH}/tree/main/docs/adr`]]} />
              <Col i={2} title="Check the numbers" items={[["Lab notebook", `${base}/results/`], ["Latest report", report], ["Progress log", doc("docs/PROGRESS.md")]]} />
            </div>
          </div>
        </section>

        {/* ── get started: a dark band ── */}
        <section id="start" className="relative mt-[140px] overflow-hidden bg-term text-term-fg">
          <div className={`${COL} relative grid items-center gap-12 py-24 lg:grid-cols-[1fr_1.15fr]`}>
            <div>
              <div className="fx label text-term-dim">Get started</div>
              <h2 className="fx title mt-4 text-[40px] sm:text-[56px]" style={v(1)}>
                <span className="text-amber-fill">Try it</span> in a few minutes.
              </h2>
              <p className="fx mt-5 max-w-[42ch] text-[16.5px] leading-[1.6] text-term-dim" style={v(2)}>
                The keyless demo runs the whole pipeline with a scripted model and mocked integrations — no API keys, no
                accounts.
              </p>
              <div className="fx mt-8 flex flex-wrap gap-2" style={v(3)}>
                <a href={GH} className="inline-flex h-9 items-center gap-2.5 rounded-[5px] bg-amber-fill px-4 text-[13.5px] font-semibold text-ink transition-transform active:translate-y-px">
                  Star on GitHub
                  <kbd className="grid h-[18px] min-w-[18px] place-items-center rounded-[3px] border border-ink/30 px-1 font-mono text-[10px] text-ink/80">G</kbd>
                </a>
                <a href={`${GH}#-quickstart`} className="inline-flex h-9 items-center rounded-[5px] border border-term-line px-4 text-[13.5px] font-semibold text-term-fg transition-colors hover:border-term-dim">
                  Quickstart →
                </a>
              </div>
            </div>
            <div className="typed fx overflow-hidden rounded-[6px] border border-term-line bg-term-panel shadow-[0_40px_80px_-30px_rgba(0,0,0,0.6)]" style={v(2)}>
              <div className="flex items-center border-b border-term-line px-4 py-3">
                <span className="font-mono text-[11px] text-term-dim">~/DebugAssist</span>
              </div>
              <div className="overflow-x-auto p-5 font-mono text-[12.5px] leading-[1.9]">
                {TERMINAL.map(([cmd, note], i) => (
                  <div key={cmd} className="type-line whitespace-nowrap" style={v(i)}>
                    <span className="text-amber-fill">$</span> {cmd}
                    {note && <span className="text-term-dim">  # {note}</span>}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* ── FAQ ── */}
        <section id="faq" className={`${COL} scroll-mt-20 pt-[140px]`}>
          <div className="grid gap-10 md:grid-cols-[1fr_1.7fr]">
            <div>
              <div className="label text-t3">FAQ</div>
              <H2 className="mt-4">Questions &amp; answers</H2>
            </div>
            <div className="border-t border-line">
              {FAQ.map(([q, a], i) => (
                <details key={q} className="fx group border-b border-line" style={v(i)}>
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-4 py-5 text-[16px] font-medium text-t1 transition-colors hover:text-t2">
                    {q}
                    <span className="grid h-6 w-6 shrink-0 place-items-center rounded-[4px] border border-line font-mono text-t3 transition-transform duration-300 group-open:rotate-45">+</span>
                  </summary>
                  <p className="max-w-[64ch] pb-5 text-[14.5px] leading-[1.65] text-t3">{a}</p>
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

function Pills({ title, items, muted }: { title: string; items: string[]; muted?: boolean }) {
  return (
    <Panel className={`p-6 ${muted ? "bg-sunk/60" : ""}`}>
      <div className="font-mono text-[11px] uppercase tracking-[0.04em] text-t3">{title}</div>
      <div className="mt-4 flex flex-wrap gap-1.5">
        {items.map((i, k) => (
          <span
            key={i}
            className={`fx inline-flex h-8 items-center rounded-full border px-3 text-[13px] transition-colors ${muted ? "border-dashed border-line-2 text-t3" : "border-line bg-surface text-t2 hover:border-line-strong hover:text-t1"}`}
            style={{ ["--i" as string]: k * 0.5 }}
          >
            {i}
          </span>
        ))}
      </div>
    </Panel>
  );
}

function Col({ title, items, i }: { title: string; items: [string, string | null][]; i: number }) {
  return (
    <div className="fx bg-raised p-6" style={{ ["--i" as string]: i }}>
      <div className="title text-[20px] tracking-[-0.015em]">{title}</div>
      <ul className="mt-3 space-y-2 text-[13.5px] text-t2">
        {items.map(([t, href]) => (
          <li key={t} className="flex items-center gap-2">
            <span className="inline-block h-[3px] w-[3px] rounded-full bg-t3" />
            {href ? (
              <a className="underline decoration-line-2 underline-offset-2 hover:text-t1" href={href}>
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
