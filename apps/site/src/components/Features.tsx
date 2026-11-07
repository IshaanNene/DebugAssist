import type { ReactNode } from "react";

// Feature cards: a title, one sentence, and a small flat drawing of the thing itself. Colour is data here as
// everywhere: violet for LLM work, teal for a Clef decision, amber for an action, green for a check that passed.
function Art({ children }: { children: ReactNode }) {
  return <div className="mt-5 grid min-h-[176px] place-items-center border-t border-line bg-sunk/60 px-6 py-7">{children}</div>;
}

const slab = "rounded-[3px] border border-line-2 bg-raised px-3 py-2 font-mono text-[11px] text-t1";

const FEATURES: { title: string; body: string; art: ReactNode }[] = [
  {
    title: "Evidence-backed root cause",
    body: "Every claim cites the evidence it rests on, and each claim is checked against that evidence before anyone reads it.",
    art: (
      <div className="space-y-2.5">
        <div className={slab}>routeV2 skips await whenHydrated()</div>
        <div className="ml-8 space-y-1.5 font-mono text-[10px]">
          <div className="text-good">✓ ev_code · grounded</div>
          <div className="text-good">✓ ev_flags · grounded</div>
          <div className="text-bad">✗ ev_logs · dropped</div>
        </div>
      </div>
    ),
  },
  {
    title: "Proof before a pull request",
    body: "A test that fails on the shipped release, a fix that makes it pass, the suite and the repo's own CI green.",
    art: (
      <div className="space-y-2.5">
        <div className={`${slab} flex justify-between`}>
          <span>fails on release</span>
          <span className="text-bad">✗</span>
        </div>
        <div className={`${slab} ml-5 flex justify-between`}>
          <span>passes with fix</span>
          <span className="text-good">✓</span>
        </div>
        <div className={`${slab} ml-10 flex justify-between`}>
          <span>suite · lint · CI</span>
          <span className="text-good">✓</span>
        </div>
      </div>
    ),
  },
  {
    title: "Clef decides, on the record",
    body: "Priority, category, rollback, test tier, retry, ship: decision templates on Cloudflare Clef, mapped by policy to act, escalate or a safe default.",
    art: (
      <div className="space-y-3">
        <div className={slab}>D11 · roll back the flag?</div>
        <div className="relative h-3 rounded-[2px] border border-line-2 bg-raised">
          <div className="absolute inset-y-0 left-0 w-[86%] bg-clef" />
          <div className="absolute -top-1.5 -bottom-1.5 left-[74%] border-l-[1.5px] border-t1" />
        </div>
        <div className="flex justify-between font-mono text-[10px] text-t3">
          <span>p</span>
          <span>p ≥ τ → act</span>
        </div>
      </div>
    ),
  },
  {
    title: "Sandboxed and policy-gated",
    body: "Agents work in a network-less container on a git worktree the host reads only through guards — no symlinks out, no .git, no secrets. Dependencies install once per lockfile and are copied into later runs. Every write — PR, ticket, flag — passes a policy gate and an audit log.",
    art: (
      <div className="grid grid-cols-2 gap-2.5">
        <div className={slab}>--network none</div>
        <div className={slab}>git worktree</div>
        <div className={`${slab} col-span-2 !border-amber !bg-tint`}>policy gate · bot branches only</div>
        <div className={slab}>install cache</div>
        <div className={slab}>audit log</div>
      </div>
    ),
  },
  {
    title: "Every run, live",
    body: "A dashboard draws each run as its fixed graph, with every model call, tool call and Clef decision, and their cost and latency.",
    art: (
      <div className="flex flex-wrap items-center gap-2">
        {["ingest", "triage", "rca", "fix", "validate"].map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <div className={`${slab} ${s === "rca" || s === "fix" ? "!border-llm" : ""}`}>{s}</div>
            {i < 4 && <span className="text-t3">→</span>}
          </div>
        ))}
      </div>
    ),
  },
  {
    title: "A harness, not a prompt",
    body: "Agent types per kind of issue, plugins of skills loaded on demand, domain knowledge bases, and a packaged runtime per agent type.",
    art: (
      <div className="relative h-40">
        {["perf-and-battery", "backend-fixes", "web-client-fixes", "test-planning", "pr-authoring"].map((s, i) => (
          <div key={s} className={`${slab} absolute`} style={{ left: i * 14, top: i * 26 }}>
            {s}
          </div>
        ))}
      </div>
    ),
  },
  {
    title: "Culprit commit, proven by running it",
    body: "The validated reproduction test goes back through history — earlier releases until it passes, then git bisect — so “introduced by” is a result, not a guess.",
    art: (
      <div className="space-y-2.5">
        <div className={`${slab} flex justify-between`}>
          <span>v3.0.4 · test</span>
          <span className="text-good">passes</span>
        </div>
        <div className={`${slab} ml-5 flex justify-between !border-amber`}>
          <span>d8813b6 · first bad</span>
          <span className="text-amber">◆</span>
        </div>
        <div className={`${slab} ml-10 flex justify-between`}>
          <span>release · test</span>
          <span className="text-bad">fails</span>
        </div>
      </div>
    ),
  },
  {
    title: "On your own repositories",
    body: "Install the GitHub App, add a pipeline config, label an issue: DebugAssist comments the root cause on it and opens a draft PR from a bot branch.",
    art: (
      <div className="space-y-2.5">
        <div className={`${slab} inline-block !border-amber !bg-tint`}>label · debugassist</div>
        <div className={`${slab} ml-6`}>comment · root cause</div>
        <div className={`${slab} ml-12`}>draft PR · debugassist/…</div>
      </div>
    ),
  },
];

export function Features() {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {FEATURES.map((f, i) => (
        <div key={f.title} className="fx panel flex flex-col overflow-hidden" style={{ ["--i" as string]: i % 2 }}>
          <div className="px-6 pt-6">
            <h3 className="title text-[21px] tracking-[-0.02em] text-t1">{f.title}</h3>
            <p className="mt-2 max-w-[52ch] text-[14.5px] leading-[1.55] text-t2">{f.body}</p>
          </div>
          <div className="mt-auto">
            <Art>{f.art}</Art>
          </div>
        </div>
      ))}
    </div>
  );
}
