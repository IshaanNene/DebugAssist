import { LiveRun, Motion, Shortcuts } from "@/components/client";
import { Architecture } from "@/components/Architecture";
import { Features } from "@/components/Features";
import { Loop } from "@/components/Loop";
import { Results } from "@/components/Results";
import { Box, Button, Dot, GH, H2, Lead, Mark, doc } from "@/components/ui";
import { contextArms, contextAudit, facts, featuredRun, results, type ContextArm, type Row } from "@/lib/data";

const pct = (x: number) => `${Math.round(x * 100)}%`;
const COL = "mx-auto w-full max-w-[1200px] px-4 sm:px-8";

export default function Home() {
  const data = results();
  const ctx = contextAudit();
  const f = facts();
  const run = featuredRun(data);
  const latest = data.arms[data.arms.length - 1];
  const passed = (rows: Row[]) => rows.filter((r) => r.hidden_tests === "True").length;
  const base = Object.fromEntries(data.baseline.map((r) => [r.bug, r]));
  const latestPrev = latest ? latest.rows.map((r) => base[r.bug]).filter(Boolean) : [];
  const report = doc(`evals/reports/${data.report}/report.md`);
  const v = (i: number) => ({ ["--i" as string]: i });
  const arms = contextArms();
  // the context-engineering arms, in the order they were measured; fix-quality is the code they re-ran
  const ARM_ORDER = ["fix-quality", "lean", "clear"];
  const ctxArms = ARM_ORDER.map((n) => arms.find((a) => a.arm === n)).filter((a): a is ContextArm => !!a);
  const before = ctxArms.find((a) => a.arm === "fix-quality");

  return (
    <>
      <Motion />
      <Shortcuts map={{ g: GH, d: doc("README.md"), r: "#results", s: "#start" }} />

      {before && ctxArms.length > 1 ? (
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
            tests passing {passed(latestPrev)} → {passed(latest.rows)} on {latest.rows.length} bugs ·{" "}
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
                    A crash or a rider&apos;s bug report goes in. Triage, an evidence-backed root cause, a mitigation, a
                    test that fails on the shipped release, the fix and its proof come out — as a pull request. Measured
                    on a bug catalog, with every number generated.
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
            Four phases, twelve steps, always in this order. Clef makes each judgement call with a calibrated
            probability, LLM agents reason and write code, and deterministic code performs every write — behind a policy
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
                <li>Crash-data bugs — locale and currency edge cases, a nil-map panic, a removed await, a battery-draining poller — fixed with a passing hidden test.</li>
                <li>Following a rider&apos;s report into the backend, and moving the fix to the service that holds the defect.</li>
                <li>Saying &ldquo;not our bug&rdquo; for a carrier outage or intended behaviour.</li>
              </ul>
            </Box>
            <Box stripes className="fx p-6" >
              <div className="font-mono text-[11px] uppercase tracking-[0.04em] text-bad">✗ What doesn&apos;t, yet</div>
              <ul className="mt-4 space-y-3 text-[14.5px] leading-[1.55] text-t2">
                <li>Validated is not always correct: some fixes pass the agent&apos;s own test but not the hidden one.</li>
                <li>Evidence the client never sees: a CORS failure is only &ldquo;Failed to fetch&rdquo; from the app.</li>
                <li>One seed per bug: the same bug can pass in one run and miss in the next.</li>
              </ul>
            </Box>
          </div>
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
            <Pills title="Target languages & tools" items={["TypeScript · React", "Python · FastAPI", "Go", "Playwright", "GitHub", "Unleash", "Docker"]} stack="middle" />
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
              <Col i={0} title="Self-host it" items={[["make up — app, telemetry, sources", null], ["MIT licensed", null], ["mock mode, no keys needed", null]]} />
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
  "fix-quality": { cls: "bg-line-strong", what: "the code both experiments re-ran" },
  lean: { cls: "bg-mark border border-line-strong", what: "file reads capped at 120 lines, an outline tool, long logs offloaded" },
  clear: { cls: "bg-[#8b7cf0] border border-line-strong", what: "old tool results replaced by one-line stubs, in batches" },
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
          Following the audit we tried two techniques on the same {arms[0].runs} bugs. Capping reads made agents read
          more often. Clearing old tool results cut tokens per turn, but each clearing rewrites the cached prefix, so
          the cache hit rate fell and cost barely moved. Both stay opt-in switches.{" "}
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
  "The plan is code, not a prompt. Models never choose the next step. Clef makes every judgement call with a calibrated probability, agents reason and write the code, and deterministic code performs every write.";

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
  ["Does an LLM decide what happens next?", "No. The plan is a fixed graph in code. LLM agents reason and write code inside steps; every judgement call is a Clef decision with a calibrated probability, mapped to act, escalate or a safe default by policy; deterministic code performs every write."],
  ["Can it change production on its own?", "Writes go through a policy gate and an audit log. It pushes only to bot branches of the demo repositories, flag rollbacks need approval, and every integration is dry-run unless configured otherwise."],
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
