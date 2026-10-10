import { Features } from "@/components/Features";
import { Loop } from "@/components/Loop";
import { Results } from "@/components/Results";
import { contextAudit, facts, results } from "@/lib/data";

const GH = "https://github.com/IshaanNene/DebugAssist";
const pct = (x: number) => `${Math.round(x * 100)}%`;

export default function Home() {
  const data = results();
  const ctx = contextAudit();
  const f = facts();
  const doc = (p: string) => `${GH}/blob/main/${p}`;
  return (
    <>
      <Nav />
      <main className="mx-auto max-w-6xl px-4 sm:px-6">
        {/* ---------- hero ---------- */}
        <section className="frame mt-6">
          <span className="frame-corners" />
          <div className="border-b border-line px-4 py-3 flex flex-wrap justify-center gap-x-8 gap-y-1 text-sm text-muted">
            <span>
              <b className="text-ink">{data.catalog.total}</b>-bug evaluation catalog
            </span>
            <span>
              <b className="text-ink">{f.templates}</b> Clef decision templates
            </span>
            <span>
              <b className="text-ink">{f.mcpServers}</b> MCP servers · <b className="text-ink">{f.mcpTools}</b> tools
            </span>
            <span>MIT licensed</span>
          </div>
          <div className="px-6 py-16 sm:py-24 text-center">
            <h1 className="text-5xl sm:text-7xl font-semibold tracking-tight leading-[1.05]">
              <span className="mark">An autonomous</span>
              <br />
              <span className="mark">on-call engineer</span>
            </h1>
            <p className="mx-auto mt-8 max-w-2xl text-lg sm:text-xl text-ink-2 leading-relaxed">
              A crash or a rider&apos;s bug report goes in. Triage, an evidence-backed root cause, a mitigation, a test
              that fails on the shipped release, the fix, the proof — and a pull request — come out. Measured on a bug
              catalog, with every number generated.
            </p>
            <div className="mt-10 flex flex-wrap justify-center gap-3">
              <a href={GH} className="bg-ink text-paper px-5 py-3 font-medium inline-flex items-center gap-3">
                View on GitHub
              </a>
              <a href="#results" className="border border-ink-2 bg-panel px-5 py-3 font-medium inline-flex items-center gap-3">
                See the results
              </a>
              <a href={`${GH}#-quickstart`} className="border border-line bg-panel px-5 py-3 inline-flex items-center gap-3">
                Run the keyless demo
              </a>
            </div>
          </div>
        </section>

        {/* ---------- loop ---------- */}
        <section id="how" className="mt-28">
          <h2 className="text-4xl sm:text-5xl font-semibold tracking-tight">
            <span className="mark">Signal in, proof out</span> — a fixed plan.
          </h2>
          <p className="mt-4 max-w-3xl text-lg text-ink-2 leading-relaxed">
            The plan is code, not a prompt: models never choose the next step. Clef makes every judgement call with a
            calibrated probability, LLM agents reason and write code, and deterministic code acts — behind a policy gate.
          </p>
          <div className="mt-8">
            <Loop />
          </div>
        </section>

        {/* ---------- features ---------- */}
        <section id="features" className="mt-28">
          <h2 className="text-4xl sm:text-5xl font-semibold tracking-tight">
            Everything an on-call engineer does, <span className="mark">with receipts.</span>
          </h2>
          <div className="mt-10">
            <Features />
          </div>
        </section>

        {/* ---------- results ---------- */}
        <section id="results" className="mt-28">
          <h2 className="text-4xl sm:text-5xl font-semibold tracking-tight">
            <span className="mark">Measured</span>, not claimed.
          </h2>
          <p className="mt-4 max-w-3xl text-lg text-ink-2 leading-relaxed">
            {data.catalog.total} bugs injected into a small ride-hailing app as natural-looking release commits —{" "}
            {data.catalog.code} that need a code fix, {data.catalog.notOurs} where the right answer is to route it. The
            agent never sees the answer key; an evaluator scores its root cause and runs hidden tests on its fix. Built
            from{" "}
            <a className="underline" href={doc(`evals/reports/${data.report}/report.md`)}>
              evals/reports/{data.report}
            </a>
            .
          </p>
          <div className="mt-8">
            <Results data={data} />
          </div>
          <div className="mt-8 grid md:grid-cols-2 gap-4">
            <div className="frame p-5">
              <span className="frame-corners" />
              <h3 className="font-semibold text-lg">What works</h3>
              <ul className="mt-3 space-y-2 text-ink-2 list-disc pl-5">
                <li>Crash-data bugs: locale and currency edge cases, a nil-map panic, a removed await, a battery-draining poller — root cause, reproduction and a fix that passes the hidden test.</li>
                <li>Following a rider&apos;s report into the backend, and moving the fix to the service that holds the defect.</li>
                <li>Saying &ldquo;not our bug&rdquo; for a carrier outage or intended behaviour — routed, not &ldquo;fixed&rdquo;.</li>
              </ul>
            </div>
            <div className="frame p-5 hatch">
              <span className="frame-corners" />
              <h3 className="font-semibold text-lg">What doesn&apos;t, yet</h3>
              <ul className="mt-3 space-y-2 text-ink-2 list-disc pl-5">
                <li>Validated is not always correct: some fixes pass the agent&apos;s own test but not the hidden one.</li>
                <li>Evidence the client never sees: a CORS failure is only &ldquo;Failed to fetch&rdquo; from the app.</li>
                <li>Small numbers: one seed per bug — read it as strengths and gaps, not precise rates.</li>
              </ul>
            </div>
          </div>
        </section>

        {/* ---------- context ---------- */}
        {ctx && (
          <section id="context" className="mt-28">
            <h2 className="text-4xl sm:text-5xl font-semibold tracking-tight">
              Where the <span className="mark">tokens</span> go.
            </h2>
            <p className="mt-4 max-w-3xl text-lg text-ink-2 leading-relaxed">
              Every agent turn re-sends the prompt, the tools and the history. The context audit splits{" "}
              {(ctx.inputTokens / 1e6).toFixed(1)}M input tokens from real runs by what they carried — and tells us which
              context-engineering technique is worth building.
            </p>
            <div className="mt-8 grid md:grid-cols-4 gap-3">
              <Stat value={pct(ctx.toolsShare)} label="tool results, re-sent on later turns" />
              <Stat value={pct(ctx.prefixShare)} label="the fixed prefix (prompt, tools, task)" />
              <Stat value={pct(ctx.modelShare)} label="the model's own messages" />
              <Stat value={pct(ctx.cacheShare)} label="served from the prompt cache" />
            </div>
            <div className="mt-4 frame p-5">
              <span className="frame-corners" />
              <div className="font-mono text-xs uppercase tracking-wider text-muted">heaviest tools (share of all input)</div>
              <div className="mt-3 space-y-2">
                {ctx.topTools.map((t) => (
                  <div key={t.tool} className="flex items-center gap-3">
                    <span className="w-36 font-mono text-sm">{t.tool}</span>
                    <div className="flex-1 h-3 border border-line bg-panel">
                      <div className="h-full bg-mark" style={{ width: pct(t.share / ctx.topTools[0].share) }} />
                    </div>
                    <span className="w-12 text-right font-mono text-sm text-muted">{pct(t.share)}</span>
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}

        {/* ---------- stack ---------- */}
        <section id="stack" className="mt-28">
          <h2 className="text-4xl sm:text-5xl font-semibold tracking-tight">
            Works with <span className="mark">your stack.</span>
          </h2>
          <p className="mt-4 max-w-3xl text-lg text-ink-2 leading-relaxed">
            Any OpenAI-compatible model, OpenTelemetry for telemetry, MCP for evidence. Every integration has a mock, so
            the whole pipeline runs without a single key.
          </p>
          <div className="mt-8 grid md:grid-cols-2 gap-4">
            <Pills title="Evidence (MCP servers)" items={["crash analytics", "code search", "git history", "feature flags", "bug reports", "logging", "tracing", "metrics & profiles", "incidents", "releases", "Jira"]} />
            <Pills title="Models & decisions" items={["Cloudflare Clef", "OpenRouter", "GroqCloud", "any OpenAI-compatible API", "LangGraph", "LangChain"]} />
            <Pills title="Telemetry" items={["OpenTelemetry", "Jaeger", "Loki", "Prometheus", "Phoenix traces"]} />
            <Pills title="Target languages & tools" items={["TypeScript / React", "Python / FastAPI", "Go", "Playwright", "GitHub", "Unleash", "Docker"]} />
          </div>
          <Pills className="mt-4" title="On the roadmap" items={["Langfuse", "LiteLLM", "Ollama / vLLM", "Promptfoo", "GlitchTip", "SWE-bench Lite"]} muted />
        </section>

        {/* ---------- open source ---------- */}
        <section id="open" className="mt-28 grid md:grid-cols-3 gap-4">
          <div className="md:col-span-3">
            <h2 className="text-4xl sm:text-5xl font-semibold tracking-tight">
              Open platform. <span className="mark">Open process.</span>
            </h2>
          </div>
          <Card title="Self-host the whole system">
            One <code className="font-mono text-sm">make up</code> brings up the app under test, its telemetry, the crash
            and bug-report sources, and DebugAssist. MIT licensed.
          </Card>
          <Card title="Every problem, written down">
            Each bug we hit while building it — symptom, cause, fix, and the test that guards it — in{" "}
            <a className="underline" href={doc("docs/LESSONS.md")}>
              lessons learned
            </a>
            .
          </Card>
          <Card title="A roadmap you can check">
            Context engineering, integrations and scale — each item measured by an eval arm, in the{" "}
            <a className="underline" href={doc("docs/ROADMAP.md")}>
              roadmap
            </a>
            .
          </Card>
        </section>

        {/* ---------- FAQ ---------- */}
        <section id="faq" className="mt-28">
          <h2 className="text-4xl font-semibold tracking-tight">Questions &amp; answers</h2>
          <div className="mt-6 divide-y divide-line border-y border-line">
            {FAQ.map(([q, a]) => (
              <details key={q} className="group py-4">
                <summary className="cursor-pointer list-none flex justify-between items-center text-lg font-medium">
                  {q}
                  <span className="font-mono text-muted group-open:rotate-45 transition-transform">+</span>
                </summary>
                <p className="mt-3 text-ink-2 leading-relaxed max-w-3xl">{a}</p>
              </details>
            ))}
          </div>
        </section>

        {/* ---------- CTA ---------- */}
        <section className="frame mt-28 px-6 py-16 text-center">
          <span className="frame-corners" />
          <h2 className="text-4xl sm:text-5xl font-semibold tracking-tight">
            <span className="mark">Try it</span> in a few minutes.
          </h2>
          <pre className="mx-auto mt-8 max-w-xl text-left font-mono text-sm bg-ink text-paper p-5 overflow-x-auto">
{`git clone --recurse-submodules ${GH}
make bootstrap && make up && make flags
make demo-push-crash   # keyless: scripted LLM, mocks
make dashboard         # http://localhost:3000`}
          </pre>
          <div className="mt-8 flex justify-center gap-3">
            <a href={GH} className="bg-ink text-paper px-5 py-3 font-medium">Star on GitHub</a>
            <a href={`${GH}#-quickstart`} className="border border-ink-2 bg-panel px-5 py-3 font-medium">Quickstart</a>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}

const FAQ: [string, string][] = [
  ["What is DebugAssist?", "An open-source pipeline that does what an on-call engineer does when something breaks: it notices the crash or the rider's report, triages it, finds the root cause with evidence, proposes a mitigation, writes a test that fails on the shipped release, fixes the code, proves the fix, and opens a pull request — or says it isn't our bug and routes it."],
  ["Does an LLM decide what happens next?", "No. The plan is a fixed graph in code. LLM agents reason and write code inside steps; every judgement call is a Clef decision with a calibrated probability mapped to act, escalate or a safe default by policy; deterministic code performs every write."],
  ["Can it change production on its own?", "Writes go through a policy gate and an audit log. Pushes only to bot branches of the demo repositories, flag rollbacks need approval, and every integration is dry-run unless configured otherwise."],
  ["How are the results measured?", "Each catalog bug is injected as a natural-looking commit, triggered by simulated riders, and discovered by the crash and bug-report sources. The agent's root cause is scored against an answer key it never sees, and hidden tests run on its fix. Every number on this page is read from the generated reports at build time."],
  ["Which models does it use?", "Any OpenAI-compatible API; the evaluation ran on openai/gpt-6-luna through OpenRouter. Decisions run on Cloudflare Clef."],
  ["Is it affiliated with Uber, Cloudflare or anyone named here?", "No. It is an independent project inspired by a public talk on MCP-powered crash investigation. Vitals and BugDrop are its own stand-ins for crash analytics and in-app bug reports."],
];

function Nav() {
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-paper/85 backdrop-blur">
      <div className="mx-auto max-w-6xl px-4 sm:px-6 h-14 flex items-center justify-between">
        <a href="#" className="font-semibold tracking-tight text-lg">
          Debug<span className="bg-mark px-0.5">Assist</span>
        </a>
        <nav className="hidden sm:flex gap-6 text-sm text-ink-2">
          <a href="#how">How it works</a>
          <a href="#results">Results</a>
          <a href="#context">Context</a>
          <a href="#stack">Stack</a>
          <a href="#faq">FAQ</a>
        </nav>
        <a href={GH} className="text-sm border border-ink-2 px-3 py-1.5 bg-panel">GitHub</a>
      </div>
    </header>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="frame p-5">
      <span className="frame-corners" />
      <div className="text-4xl font-semibold tracking-tight">{value}</div>
      <div className="mt-1 text-sm text-muted">{label}</div>
    </div>
  );
}

function Pills({ title, items, muted, className = "" }: { title: string; items: string[]; muted?: boolean; className?: string }) {
  return (
    <div className={`frame p-5 ${muted ? "hatch" : ""} ${className}`}>
      <span className="frame-corners" />
      <h3 className="text-lg font-medium">{title}</h3>
      <div className="mt-4 flex flex-wrap gap-2">
        {items.map((i) => (
          <span key={i} className={`border px-3 py-1.5 text-sm bg-panel ${muted ? "border-dashed border-line text-muted" : "border-line"}`}>
            {i}
          </span>
        ))}
      </div>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="frame p-5">
      <span className="frame-corners" />
      <h3 className="text-lg font-medium">{title}</h3>
      <p className="mt-2 text-ink-2 leading-relaxed">{children}</p>
    </div>
  );
}

function Footer() {
  return (
    <footer className="mt-28 border-t border-line">
      <div className="mx-auto max-w-6xl px-4 sm:px-6 py-10 text-sm text-muted flex flex-col sm:flex-row justify-between gap-4">
        <span>DebugAssist · MIT licensed · independent open-source project</span>
        <span>
          Not affiliated with Uber, Cloudflare, OpenAI, OpenRouter or Groq; names indicate integrations only.
        </span>
      </div>
    </footer>
  );
}
