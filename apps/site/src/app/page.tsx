import { Reveal, Shortcuts } from "@/components/client";
import { Features } from "@/components/Features";
import { Loop } from "@/components/Loop";
import { Results } from "@/components/Results";
import { Box, Button, Dot, GH, H2, Lead, Mark, doc } from "@/components/ui";
import { contextAudit, facts, results, type Row } from "@/lib/data";

const pct = (x: number) => `${Math.round(x * 100)}%`;
const COL = "mx-auto w-full max-w-[880px] px-4 sm:px-6";

export default function Home() {
  const data = results();
  const ctx = contextAudit();
  const f = facts();
  const latest = data.arms[data.arms.length - 1];
  const passed = (rows: Row[]) => rows.filter((r) => r.hidden_tests === "True").length;
  const base = Object.fromEntries(data.baseline.map((r) => [r.bug, r]));
  const latestPrev = latest ? latest.rows.map((r) => base[r.bug]).filter(Boolean) : [];
  const report = doc(`evals/reports/${data.report}/report.md`);

  return (
    <>
      <Shortcuts map={{ g: GH, d: doc("README.md"), r: "#results", s: "#start" }} />

      {latest && (
        <a href={report} className="block border-b border-line bg-surface-1 py-2 text-center text-[12.5px] text-t2 hover:text-t1">
          <span className="font-mono text-[10.5px] uppercase tracking-[0.05em] text-t3">latest re-run · {latest.name}</span>{" "}
          · hidden tests passing {passed(latestPrev)} → {passed(latest.rows)} on {latest.rows.length} bugs ·{" "}
          <span className="underline underline-offset-2">read the report</span>
        </a>
      )}

      <header className="sticky top-0 z-30 border-b border-line bg-surface/85 backdrop-blur">
        <div className={`${COL} flex h-12 items-center justify-between`}>
          <a href="#" className="flex items-center gap-2 font-display text-[15px] font-semibold tracking-[-0.02em]">
            <span className="grid h-5 w-5 place-items-center border border-t1 bg-mark font-mono text-[10px]">D</span>
            DebugAssist
          </a>
          <nav className="hidden gap-5 text-[12.5px] text-t3 md:flex">
            <a className="hover:text-t1" href="#how">How it works</a>
            <a className="hover:text-t1" href="#results">Results</a>
            <a className="hover:text-t1" href="#tokens">Tokens</a>
            <a className="hover:text-t1" href="#stack">Stack</a>
            <a className="hover:text-t1" href="#faq">FAQ</a>
          </nav>
          <Button href={GH} hint="G">GitHub</Button>
        </div>
      </header>

      <main className="hero-bg">
        {/* ── hero ── */}
        <section className={`${COL} pt-8 md:pt-14`}>
          <Box stack="first">
            <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 px-4 py-2.5 text-[13px] text-t3">
              <span>
                <b className="font-medium text-t1">{data.catalog.total}</b>-bug evaluation catalog
              </span>
              <Dot />
              <span>
                <b className="font-medium text-t1">{f.templates}</b> Clef decision templates
              </span>
              <Dot />
              <span>
                <b className="font-medium text-t1">{f.mcpServers}</b> MCP servers · <b className="font-medium text-t1">{f.mcpTools}</b> tools
              </span>
            </div>
          </Box>
          <Box stack="middle" className="px-5 py-14 text-center sm:py-20">
            <h1 className="flex flex-col items-center gap-1 font-display text-[40px] font-medium leading-[1.04] tracking-[-0.03em] text-t1 sm:text-[56px] md:text-[68px]">
              <Mark>An autonomous</Mark>
              <Mark>on-call engineer</Mark>
            </h1>
            <p className="mx-auto mt-8 max-w-[54ch] text-[15px] leading-[1.55] text-t3">
              A crash or a rider&apos;s bug report goes in. Triage, an evidence-backed root cause, a mitigation, a test
              that fails on the shipped release, the fix and its proof come out — as a pull request. Measured on a bug
              catalog, with every number generated.
            </p>
            <div className="mt-8 flex flex-wrap justify-center gap-2">
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
          </Box>
          <Box stack="last">
            <div className="grid grid-cols-3 gap-px bg-line sm:grid-cols-6">
              {[
                ["Vitals", "crash analytics"],
                ["BugDrop", "bug reports"],
                ["Clef", "decisions"],
                ["LangGraph", "fixed plan"],
                ["MCP", "evidence"],
                ["OpenTelemetry", "telemetry"],
                ["Jaeger", "traces"],
                ["Loki", "logs"],
                ["Unleash", "flags"],
                ["GitHub", "pull requests"],
                ["Jira", "tickets"],
                ["Docker", "sandbox"],
              ].map(([name, role]) => (
                <div key={name} className="flex flex-col items-center justify-center bg-surface px-2 py-4">
                  <span className="font-display text-[15px] font-medium tracking-[-0.01em] text-t2">{name}</span>
                  <span className="mt-0.5 font-mono text-[9.5px] uppercase tracking-[0.05em] text-t4">{role}</span>
                </div>
              ))}
            </div>
          </Box>
        </section>

        {/* ── the loop ── */}
        <Reveal id="how" className={`${COL} pt-[120px]`}>
          <H2>
            Investigate, fix, prove — <Mark>repeat.</Mark>
          </H2>
          <Lead className="mt-4">
            The plan is code, not a prompt: models never choose the next step. Clef makes each judgement call with a
            calibrated probability, LLM agents reason and write code, and deterministic code performs every write —
            behind a policy gate.
          </Lead>
          <div className="mt-10">
            <Loop />
          </div>
        </Reveal>

        {/* ── features ── */}
        <Reveal id="features" className={`${COL} pt-[120px]`}>
          <H2 className="max-w-[20ch]">
            Everything an on-call engineer does, <Mark>with receipts.</Mark>
          </H2>
          <Lead className="mt-4">One pipeline from the first crash report to a merged fix, with evidence at every step.</Lead>
          <div className="mt-10">
            <Features />
          </div>
        </Reveal>

        {/* ── results ── */}
        <Reveal id="results" className={`${COL} pt-[120px]`}>
          <H2>
            <Mark>Measured</Mark>, not claimed.
          </H2>
          <Lead className="mt-4">
            {data.catalog.total} bugs injected into a small ride-hailing app as natural-looking release commits —{" "}
            {data.catalog.code} that need a code fix, {data.catalog.notOurs} where the right answer is to route it. The
            agent never sees the answer key; an evaluator scores its root cause and runs hidden tests on its fix. Built
            from{" "}
            <a className="text-t1 underline underline-offset-2" href={report}>
              evals/reports/{data.report}
            </a>
            .
          </Lead>
          <div className="mt-10">
            <Results data={data} />
          </div>
          <div className="mt-2 grid gap-2 md:grid-cols-2">
            <Box className="p-5">
              <div className="font-mono text-[11px] uppercase tracking-[0.04em] text-t3">What works</div>
              <ul className="mt-3 space-y-2.5 text-[14px] leading-[1.5] text-t2">
                <li>Crash-data bugs — locale and currency edge cases, a nil-map panic, a removed await, a battery-draining poller — fixed with a passing hidden test.</li>
                <li>Following a rider&apos;s report into the backend, and moving the fix to the service that holds the defect.</li>
                <li>Saying &ldquo;not our bug&rdquo; for a carrier outage or intended behaviour.</li>
              </ul>
            </Box>
            <Box stripes className="p-5">
              <div className="font-mono text-[11px] uppercase tracking-[0.04em] text-t3">What doesn&apos;t, yet</div>
              <ul className="mt-3 space-y-2.5 text-[14px] leading-[1.5] text-t2">
                <li>Validated is not always correct: some fixes pass the agent&apos;s own test but not the hidden one.</li>
                <li>Evidence the client never sees: a CORS failure is only &ldquo;Failed to fetch&rdquo; from the app.</li>
                <li>One seed per bug: the same bug can pass in one run and miss in the next.</li>
              </ul>
            </Box>
          </div>
        </Reveal>

        {/* ── tokens ── */}
        {ctx && (
          <Reveal id="tokens" className={`${COL} pt-[120px]`}>
            <H2>
              Where the <Mark>tokens</Mark> go.
            </H2>
            <Lead className="mt-4">
              Every agent turn re-sends the prompt, the tools and the history. A context audit split{" "}
              {(ctx.inputTokens / 1e6).toFixed(1)}M input tokens from real runs by what they carried — so we build the
              context-engineering technique the data points to, not the one that sounds best.
            </Lead>
            <div className="mt-10 cbox">
              <div className="grid grid-cols-2 gap-px bg-line md:grid-cols-4">
                {[
                  [ctx.toolsShare, "tool results, re-sent on later turns"],
                  [ctx.prefixShare, "the fixed prefix: prompt, tools, task"],
                  [ctx.modelShare, "the model's own messages"],
                  [ctx.cacheShare, "served from the prompt cache"],
                ].map(([v, l]) => (
                  <div key={l as string} className="bg-surface p-4">
                    <div className="font-display text-[28px] font-medium tracking-[-0.02em]">{pct(v as number)}</div>
                    <div className="mt-0.5 text-[12.5px] text-t3">{l}</div>
                  </div>
                ))}
              </div>
            </div>
            <div className="cbox no-top -mt-px p-5">
              <div className="font-mono text-[11px] uppercase tracking-[0.04em] text-t3">Heaviest tools · share of all input</div>
              <div className="mt-4 space-y-2.5">
                {ctx.topTools.map((t) => (
                  <div key={t.tool} className="flex items-center gap-3">
                    <span className="w-28 font-mono text-[12px] text-t2">{t.tool}</span>
                    <div className="h-2.5 flex-1 border border-line bg-surface">
                      <div className="h-full bg-mark" style={{ width: pct(t.share / ctx.topTools[0].share) }} />
                    </div>
                    <span className="w-10 text-right font-mono text-[12px] text-t3">{pct(t.share)}</span>
                  </div>
                ))}
              </div>
            </div>
          </Reveal>
        )}

        {/* ── stack ── */}
        <Reveal id="stack" className={`${COL} pt-[120px]`}>
          <H2>
            Works with <Mark>your stack.</Mark>
          </H2>
          <Lead className="mt-4">
            Any OpenAI-compatible model, OpenTelemetry for telemetry, MCP for evidence. Every integration has a mock, so
            the whole pipeline runs without a single key.
          </Lead>
          <div className="mt-10">
            <Pills title="Evidence · MCP servers" items={["crash analytics", "code search", "git history", "feature flags", "bug reports", "logging", "tracing", "metrics & profiles", "incidents", "releases", "Jira"]} stack="first" />
            <div className="-mt-px grid md:grid-cols-2">
              <Pills title="Models & decisions" items={["Cloudflare Clef", "OpenRouter", "GroqCloud", "OpenAI-compatible", "LangGraph", "LangChain"]} stack="middle" />
              <Pills title="Telemetry" items={["OpenTelemetry", "Jaeger", "Loki", "Prometheus", "Phoenix"]} stack="middle" className="md:-ml-px" />
            </div>
            <Pills title="Target languages & tools" items={["TypeScript · React", "Python · FastAPI", "Go", "Playwright", "GitHub", "Unleash", "Docker"]} stack="middle" />
            <Pills title="On the roadmap" items={["Langfuse", "LiteLLM", "Ollama · vLLM", "Promptfoo", "GlitchTip", "SWE-bench Lite"]} stack="last" muted />
          </div>
        </Reveal>

        {/* ── open ── */}
        <Reveal id="open" className={`${COL} pt-[120px]`}>
          <H2>
            Open platform. <Mark>Open process.</Mark>
          </H2>
          <div className="mt-10 cbox">
            <div className="grid gap-px bg-line md:grid-cols-3">
              <Col title="Self-host it" items={[["make up — app, telemetry, sources", null], ["MIT licensed", null], ["mock mode, no keys needed", null]]} />
              <Col title="Read the process" items={[["Lessons learned", doc("docs/LESSONS.md")], ["Architecture", doc("docs/ARCHITECTURE.md")], ["Decision records", `${GH}/tree/main/docs/adr`]]} />
              <Col title="Check the numbers" items={[["Latest report", report], ["Roadmap", doc("docs/ROADMAP.md")], ["Progress log", doc("docs/PROGRESS.md")]]} />
            </div>
          </div>
        </Reveal>

        {/* ── get started ── */}
        <Reveal id="start" className={`${COL} pt-[120px]`}>
          <Box className="px-5 py-14 text-center">
            <H2>
              <Mark>Try it</Mark> in a few minutes.
            </H2>
            <p className="mx-auto mt-4 max-w-[48ch] text-[15px] text-t3">
              The keyless demo runs the whole pipeline with a scripted model and mocked integrations.
            </p>
            <pre className="mx-auto mt-8 max-w-[620px] overflow-x-auto border border-[#333] bg-code p-5 text-left font-mono text-[12px] leading-[1.7] text-[#f3f1ea]">
{`git clone --recurse-submodules ${GH}
make bootstrap && make up && make flags
make demo-push-crash     `}<span className="text-[#9a988f]"># keyless: scripted LLM, mocks</span>{`
make dashboard           `}<span className="text-[#9a988f]"># http://localhost:3000</span>
            </pre>
            <div className="mt-8 flex justify-center gap-2">
              <Button href={GH} variant="primary" hint="G">
                Star on GitHub
              </Button>
              <Button href={`${GH}#-quickstart`}>Quickstart</Button>
            </div>
          </Box>
        </Reveal>

        {/* ── FAQ ── */}
        <Reveal id="faq" className={`${COL} pt-[120px]`}>
          <H2>Questions &amp; answers</H2>
          <div className="mt-8 border-t border-dashed border-line-dash">
            {FAQ.map(([q, a]) => (
              <details key={q} className="group border-b border-dashed border-line-dash py-4">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-[15px] font-medium text-t1">
                  {q}
                  <span className="font-mono text-t3 transition-transform group-open:rotate-45">+</span>
                </summary>
                <p className="mt-3 max-w-[64ch] text-[14px] leading-[1.6] text-t3">{a}</p>
              </details>
            ))}
          </div>
        </Reveal>
      </main>

      <footer className="mt-[120px] border-t border-line">
        <div className={`${COL} grid gap-8 py-10 text-[12.5px] sm:grid-cols-4`}>
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
        <div className={`${COL} border-t border-line py-4 text-[11.5px] text-t4`}>
          Not affiliated with Uber, Cloudflare, OpenAI, OpenRouter, Groq or any company named here; names indicate
          integrations only.
        </div>
      </footer>
    </>
  );
}

const FAQ: [string, string][] = [
  ["What is DebugAssist?", "An open-source pipeline that does what an on-call engineer does when something breaks: it notices the crash or the rider's report, triages it, finds the root cause with evidence, proposes a mitigation, writes a test that fails on the shipped release, fixes the code, proves the fix and opens a pull request — or says it isn't our bug and routes it."],
  ["Does an LLM decide what happens next?", "No. The plan is a fixed graph in code. LLM agents reason and write code inside steps; every judgement call is a Clef decision with a calibrated probability, mapped to act, escalate or a safe default by policy; deterministic code performs every write."],
  ["Can it change production on its own?", "Writes go through a policy gate and an audit log. It pushes only to bot branches of the demo repositories, flag rollbacks need approval, and every integration is dry-run unless configured otherwise."],
  ["How are the results measured?", "Each catalog bug is injected as a natural-looking commit, triggered by simulated riders, and discovered by the crash and bug-report sources. The agent's root cause is scored against an answer key it never sees, and hidden tests run on its fix. Every number on this page is read from the generated reports when the site is built."],
  ["Which models does it use?", "Any OpenAI-compatible API. The evaluation on this page ran on openai/gpt-6-luna through OpenRouter; decisions run on Cloudflare Clef."],
  ["Is it affiliated with Uber, Cloudflare or anyone named here?", "No. It is an independent project inspired by a public talk on MCP-powered crash investigation. Vitals and BugDrop are its own stand-ins for crash analytics and in-app bug reports."],
];

function Pills({ title, items, muted, stack, className = "" }: { title: string; items: string[]; muted?: boolean; stack?: "first" | "middle" | "last"; className?: string }) {
  return (
    <Box stack={stack} stripes={muted} className={`p-5 ${className}`}>
      <div className="font-mono text-[11px] uppercase tracking-[0.04em] text-t3">{title}</div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {items.map((i) => (
          <span key={i} className={`inline-flex h-7 items-center border px-2.5 text-[12.5px] ${muted ? "border-dashed border-line-dash bg-surface text-t3" : "border-line bg-surface text-t2"}`}>
            {i}
          </span>
        ))}
      </div>
    </Box>
  );
}

function Col({ title, items }: { title: string; items: [string, string | null][] }) {
  return (
    <div className="bg-surface p-5">
      <div className="font-display text-[17px] font-medium tracking-[-0.01em]">{title}</div>
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
