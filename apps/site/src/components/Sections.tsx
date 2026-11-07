import type { ReactNode } from "react";
import { Receipt } from "@/components/Receipt";
import type { WriteRule } from "@/lib/data";

// The home page's explanatory sections, drawn flat from the theme tokens. Colour is data: code is neutral,
// LLM agents violet, Clef teal, amber is time and action, green a check that passed.

const cx = (...c: (string | false | undefined)[]) => c.filter(Boolean).join(" ");

type Kind = "code" | "llm" | "clef";
const KIND: Record<Kind, { label: string; text: string; bg: string; border: string }> = {
  code: { label: "deterministic code", text: "text-code", bg: "bg-code", border: "border-code" },
  llm: { label: "LLM agents", text: "text-llm", bg: "bg-llm", border: "border-llm" },
  clef: { label: "Clef decisions", text: "text-clef", bg: "bg-clef", border: "border-clef" },
};

export function KindDot({ kind, className }: { kind: Kind; className?: string }) {
  return <span aria-hidden className={cx("inline-block h-2 w-2 shrink-0 rounded-full", KIND[kind].bg, className)} />;
}

/* ───────────────────────── The three actors ───────────────────────── */

function Actor({ kind, title, body, children }: { kind: Kind; title: ReactNode; body: string; children: ReactNode }) {
  return (
    <div className="fx flex flex-col bg-raised">
      <div className="grid h-[200px] place-items-center overflow-hidden border-b border-line bg-sunk/50 px-6">{children}</div>
      <div className="p-6">
        <div className={cx("label flex items-center gap-2", KIND[kind].text)}>
          <KindDot kind={kind} />
          {KIND[kind].label}
        </div>
        <h3 className="title mt-3 text-[26px] text-t1">{title}</h3>
        <p className="mt-2.5 text-[14.5px] leading-[1.55] text-t2">{body}</p>
      </div>
    </div>
  );
}

export function Actors({ templates }: { templates: number }) {
  return (
    <div className="grid gap-px overflow-hidden rounded-[10px] border border-line bg-line md:grid-cols-3">
      <Actor
        kind="clef"
        title="Clef decides."
        body={`Every judgement call — priority, rollback, test tier, ship — is a calibrated probability from one of ${templates} decision templates, mapped by policy to act, escalate or a safe default.`}
      >
        <div className="w-full max-w-[240px] font-mono text-[11px]">
          <div className="flex justify-between text-t3">
            <span>roll back the flag?</span>
            <span className="text-clef">p 0.02</span>
          </div>
          <div className="relative mt-2.5 h-3 rounded-[2px] bg-line">
            <div className="absolute inset-y-0 left-0 w-[6%] rounded-[2px] bg-clef" />
            <div className="absolute -bottom-1.5 -top-1.5 left-[74%] w-px bg-t1" />
          </div>
          <div className="mt-2 flex justify-between text-t3">
            <span>0</span>
            <span className="pl-[48%]">τ</span>
            <span>1</span>
          </div>
          <div className="mt-3 rounded-[3px] border border-line-2 bg-raised px-2.5 py-1.5 text-t2">→ safe default: no rollback</div>
        </div>
      </Actor>
      <Actor
        kind="llm"
        title="Agents reason."
        body="LLM agents read the evidence and write code inside one step, in a sandbox with no network. They explain and fix; they never choose what happens next."
      >
        <div className="w-full max-w-[290px] space-y-0.5 whitespace-pre font-mono text-[10.5px] leading-[1.65]">
          <div className="text-t3">{"// the fix for VIT-1001, router.ts"}</div>
          <div className="px-2 text-t3">async function routeV2(…) {"{"}</div>
          <div className="rounded-[2px] bg-good/10 px-2 text-good">{"+   await whenHydrated();"}</div>
          <div className="px-2 text-t2">{"    const state = sessionStore.getState();"}</div>
          <div className="px-2 text-t2">{"    const riderId = state.session!.riderId;"}</div>
          <div className="whitespace-normal pt-1.5 text-llm">plus a test that fails without it</div>
        </div>
      </Actor>
      <Actor
        kind="code"
        title="Code acts."
        body="The plan is a fixed graph in code. Deterministic steps gather evidence, run the tests and perform every write — through a policy gate, into an audit log."
      >
        <div className="flex w-full max-w-[250px] flex-col items-stretch gap-1.5 font-mono text-[11px]">
          {["ingest", "context_collector", "validate"].map((s) => (
            <div key={s} className="flex items-center justify-between rounded-[3px] border border-line-2 bg-raised px-2.5 py-1.5 text-t2">
              {s}
              <span className="text-good">✓</span>
            </div>
          ))}
          <div className="flex items-center justify-between rounded-[3px] border border-amber bg-tint px-2.5 py-1.5 text-t1">
            policy gate
            <span className="text-amber">→ PR</span>
          </div>
        </div>
      </Actor>
    </div>
  );
}

/* ───────────────────────── The pipeline ───────────────────────── */

interface Step {
  name: string;
  kind: Kind[];
  d?: string; // the Clef decisions taken in this step
}
interface Phase {
  name: string;
  decisions: string;
  what: string;
  parts: Step[];
}

// The fixed plan (ADR 0001) in four phases; the steps are the pipeline's own, always in this order. Each step's kinds
// and decisions follow the decision templates' `stage` (packages/decisions/templates).
const PHASES: Phase[] = [
  {
    name: "Detect",
    decisions: "D01 · D02",
    what: "A crash from Vitals or a rider's report from BugDrop comes in. Owner from CODEOWNERS, priority and severity, dedup against open issues, a ticket and a page.",
    parts: [
      { name: "Ingest", kind: ["code"] },
      { name: "Triage", kind: ["clef"], d: "D01" },
      { name: "Dedup", kind: ["clef"], d: "D02" },
    ],
  },
  {
    name: "Investigate",
    decisions: "D03 – D11",
    what: "A deterministic evidence bundle from the MCP servers; an agent and its subagents explain the defect, every claim checked against its evidence; a flag rollback when the numbers say so.",
    parts: [
      { name: "Context", kind: ["code", "clef"], d: "D03 D04" },
      { name: "Root cause", kind: ["llm", "clef"], d: "D05–D10" },
      { name: "Mitigate", kind: ["clef"], d: "D11" },
    ],
  },
  {
    name: "Fix",
    decisions: "D12 – D15",
    what: "A test that fails on the shipped release, the smallest fix that makes it pass, then proof: fails before, passes after, suite and CI green — or another attempt.",
    parts: [
      { name: "Reproduce", kind: ["llm"] },
      { name: "Fix", kind: ["llm", "clef"], d: "D12 D13" },
      { name: "Validate", kind: ["code", "clef"], d: "D14 D15" },
    ],
  },
  {
    name: "Ship",
    decisions: "D16 · D17",
    what: "A pull request or a draft, decided by the evidence and linked from the ticket. After the deploy, watch the crash rate and resolve or reopen.",
    parts: [
      { name: "Ship gate", kind: ["clef"], d: "D16" },
      { name: "Pull request", kind: ["code"] },
      { name: "Watch", kind: ["code", "clef"], d: "D17" },
    ],
  },
];

export function Pipeline() {
  return (
    <div>
      {/* the rail: signal in, proof out */}
      <div className="relative mb-6 hidden items-center lg:flex" aria-hidden>
        <span className="label pr-4 text-[10px] text-signal">signal in</span>
        <div className="relative h-px flex-1 bg-line-2">
          <svg className="absolute inset-0 h-px w-full overflow-visible" preserveAspectRatio="none">
            <line x1="0" y1="0" x2="100%" y2="0" stroke="var(--amber)" strokeWidth="1.5" strokeDasharray="4 10" className="flow" />
          </svg>
          {PHASES.map((p, i) => (
            <span
              key={p.name}
              className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-amber bg-surface"
              style={{ left: `${12.5 + i * 25}%` }}
            />
          ))}
        </div>
        <span className="label pl-4 text-[10px] text-good">proof out</span>
      </div>
      <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {PHASES.map((p, i) => (
          <li key={p.name} className="fx panel group flex flex-col p-5 transition-colors hover:border-line-strong" style={{ ["--i" as string]: i }}>
            <div className="flex items-baseline justify-between">
              <span className="font-mono text-[12px] text-amber">{String(i + 1).padStart(2, "0")}</span>
              <span className="font-mono text-[10.5px] text-t3">{p.decisions}</span>
            </div>
            <h3 className="title mt-2 text-[26px] text-t1">{p.name}</h3>
            <ul className="mt-4 space-y-1.5">
              {p.parts.map((st) => (
                <li key={st.name} className="flex items-center justify-between gap-2 rounded-[4px] border border-line bg-sunk/60 px-3 py-2">
                  <span className="flex items-center gap-2 text-[13.5px] font-medium text-t1">
                    <span className="flex gap-1">
                      {st.kind.map((k) => (
                        <KindDot key={k} kind={k} />
                      ))}
                    </span>
                    {st.name}
                  </span>
                  {st.d && <span className="font-mono text-[10.5px] text-clef">{st.d}</span>}
                </li>
              ))}
            </ul>
            <p className="mt-4 text-[13.5px] leading-[1.55] text-t2">{p.what}</p>
          </li>
        ))}
      </ol>
      <div className="mt-5 flex flex-wrap gap-x-5 gap-y-2 font-mono text-[11px] text-t3">
        {(Object.keys(KIND) as Kind[]).map((k) => (
          <span key={k} className="inline-flex items-center gap-2">
            <KindDot kind={k} />
            {KIND[k].label}
          </span>
        ))}
        <span className="text-clef">D·· a Clef decision template</span>
      </div>
    </div>
  );
}

/* ───────────────────────── The architecture ───────────────────────── */

interface Layer {
  name: string;
  blurb: string;
  blocks: [string, string][];
  core?: boolean;
}

function layers(servers: number, tools: number): Layer[] {
  // top (what acts) to bottom (what breaks)
  return [
    {
      name: "Agent core",
      core: true,
      blurb: "LangGraph runs the fixed plan; Clef makes each judgement call; LLM agents reason and write code in a network-less sandbox; a policy gate stands before every write.",
      blocks: [
        ["LangGraph", "fixed plan"],
        ["Clef", "decisions"],
        ["agents", "LLM · skills"],
        ["sandbox", "no network"],
        ["policy gate", "→ PR · ticket"],
      ],
    },
    {
      name: "Evidence",
      blurb: `${servers} MCP servers, ${tools} tools — the only way agents see the world. Each returns structured evidence with an id that claims must cite.`,
      blocks: [
        ["crashes", "Vitals · BugDrop"],
        ["code", "search · git"],
        ["telemetry", "logs · traces"],
        ["flags", "releases"],
        ["tickets", "Jira · incidents"],
      ],
    },
    {
      name: "Signals",
      blurb: "How problems surface: Vitals for crashes and performance, BugDrop for rider reports with screenshots and logs, OpenTelemetry into Jaeger, Loki and Prometheus.",
      blocks: [
        ["Vitals", "crashes · perf"],
        ["BugDrop", "rider reports"],
        ["traces", "Jaeger"],
        ["logs", "Loki"],
        ["metrics", "Prometheus"],
      ],
    },
    {
      name: "Target system",
      blurb: "MiniRide, the app the bugs live in: a React rider app, a Node GraphQL gateway, dispatch in Python and payments in Go, with feature flags from Unleash.",
      blocks: [
        ["client", "React"],
        ["gateway", "Node · GraphQL"],
        ["dispatch", "Python"],
        ["payments", "Go"],
        ["flags", "Unleash"],
      ],
    },
  ];
}

export function Layers({ servers, tools }: { servers: number; tools: number }) {
  const L = layers(servers, tools);
  return (
    <div className="grid gap-4 lg:grid-cols-[56px_minmax(0,1fr)]">
      {/* the direction of travel: problems rise, actions leave through the top */}
      <div className="hidden flex-col items-center lg:flex" aria-hidden>
        <span className="label text-[10px] text-amber [writing-mode:vertical-rl] rotate-180">actions leave</span>
        <div className="relative my-3 w-px flex-1 bg-gradient-to-t from-signal via-line-2 to-amber">
          <span className="absolute -top-1 left-1/2 -translate-x-1/2 text-[10px] leading-none text-amber">▲</span>
        </div>
        <span className="label text-[10px] text-signal [writing-mode:vertical-rl] rotate-180">problems rise</span>
      </div>
      <ol className="space-y-2">
        {L.map((layer, k) => (
          <li
            key={layer.name}
            className={cx(
              "fx grid gap-5 rounded-[10px] border p-5 md:grid-cols-[230px_minmax(0,1fr)] md:items-center",
              layer.core ? "border-amber/60 bg-tint" : "border-line bg-raised",
            )}
            style={{ ["--i" as string]: k }}
          >
            <div>
              <div className="flex items-center gap-2">
                <span className={cx("font-mono text-[11px]", layer.core ? "text-amber" : "text-t3")}>L{L.length - k}</span>
                <h3 className="title text-[21px] text-t1">{layer.name}</h3>
              </div>
              <p className="mt-1.5 text-[13px] leading-[1.5] text-t2">{layer.blurb}</p>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
              {layer.blocks.map(([label, sub]) => {
                const gate = layer.core && label === "policy gate";
                return (
                  <div
                    key={label}
                    className={cx(
                      "rounded-[6px] border px-3 py-2.5",
                      gate ? "border-amber bg-amber-fill text-ink" : "border-line-2 bg-surface",
                    )}
                  >
                    <div className={cx("font-mono text-[12.5px] font-medium", gate ? "text-ink" : "text-t1")}>{label}</div>
                    <div className={cx("mt-0.5 font-mono text-[10.5px]", gate ? "text-ink/70" : "text-t3")}>{sub}</div>
                  </div>
                );
              })}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

/* ───────────────────────── Safety ───────────────────────── */

const MODE: Record<string, { label: string; cls: string }> = {
  live: { label: "live", cls: "border-good/50 text-good" },
  approval: { label: "needs approval", cls: "border-amber/60 text-amber" },
  dry_run: { label: "dry run", cls: "border-line-2 text-t3" },
  deny: { label: "never", cls: "border-line-2 text-t3 line-through" },
};

export function Safety({ rules, branchPrefix }: { rules: WriteRule[]; branchPrefix: string }) {
  const file = "configs/policies/writes.yaml";
  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
      <div className="grid content-start gap-3">
        {[
          ["Sandboxed", "Agents work in a container with no network, on a git worktree the host reads only through guards — no symlinks out, no .git, no secrets."],
          ["Bot branches only", `Pushes go only to ${branchPrefix}* branches — never main, release branches or tags.`],
          ["Draft pull requests", "On your repositories, only once the GitHub App is installed and the repo has a .DebugAssist/pipeline.yaml."],
          ["Dry run by default", "Anything the policy does not list is recorded, not performed. Every write that does happen is audited."],
        ].map(([t, b], i) => (
          <div key={t} className="fx panel flex gap-4 p-5" style={{ ["--i" as string]: i }}>
            <span className="mt-1 grid h-6 w-6 shrink-0 place-items-center rounded-[5px] bg-tint font-mono text-[11px] text-amber">{i + 1}</span>
            <div>
              <h3 className="text-[16px] font-semibold tracking-[-0.01em] text-t1">{t}</h3>
              <p className="mt-1 text-[14px] leading-[1.55] text-t2">{b}</p>
            </div>
          </div>
        ))}
      </div>
      <div className="fx panel overflow-hidden">
        <div className="flex items-center justify-between gap-3 border-b border-line bg-sunk/60 px-5 py-3">
          <span className="font-mono text-[12px] text-t1">{file}</span>
          <span className="label text-[10px] text-t3">read at build time</span>
        </div>
        <ul className="divide-y divide-line">
          {rules.map((r) => {
            const m = MODE[r.mode] ?? { label: r.mode, cls: "border-line-2 text-t3" };
            return (
              <li key={r.action} className="flex items-center justify-between gap-4 px-5 py-2.5">
                <div className="min-w-0">
                  <div className="font-mono text-[12.5px] text-t1">{r.action}</div>
                  {r.note && <div className="truncate text-[12px] text-t3">{r.note}</div>}
                </div>
                <Receipt source={{ file, field: `actions.${r.action}`, raw: r.mode, note: r.note || undefined }} className="shrink-0 border-b-0">
                  <span className={cx("inline-flex rounded-full border px-2.5 py-0.5 font-mono text-[11px]", m.cls)}>{m.label}</span>
                </Receipt>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
