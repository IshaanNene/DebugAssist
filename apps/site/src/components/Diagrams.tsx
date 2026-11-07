import type { CSSProperties, ReactNode } from "react";
import type { FeaturedRun } from "@/lib/data";

// Technical drawings: bracketed frames, right-angle connectors with arrowheads, square mono tags. Each diagram is an
// SVG for the connectors laid under HTML frames placed in the same coordinate box, so text stays crisp. A small square
// packet rides each connector (CSS offset-path on the same path) and stops entirely under reduced motion. Below `lg`
// each drawing becomes a vertical stack.

const cx = (...c: (string | false | undefined)[]) => c.filter(Boolean).join(" ");


/** Arrowhead marker, defined once per SVG. */
export function Defs({ id }: { id: string }) {
  return (
    <defs>
      <marker id={id} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
        <path d="M0 0 L8 4 L0 8 z" fill="var(--line-strong)" />
      </marker>
    </defs>
  );
}

/** A connector with an arrowhead and, optionally, a packet travelling it. */
export function Edge({ d, arrow, packet = false, dur = 2.8, delay = 0, dashed }: { d: string; arrow?: string; packet?: boolean; dur?: number; delay?: number; dashed?: boolean }) {
  return (
    <g>
      <path d={d} fill="none" stroke="var(--line-strong)" strokeWidth={1} strokeDasharray={dashed ? "4 4" : undefined} markerEnd={arrow ? `url(#${arrow})` : undefined} />
      {packet && (
        <rect
          x={-2.5}
          y={-2.5}
          width={5}
          height={5}
          fill="var(--fg)"
          className="packet"
          style={{ offsetPath: `path("${d}")`, ["--dur"]: `${dur}s`, ["--delay"]: `${delay}s` } as CSSProperties}
        />
      )}
    </g>
  );
}

/** Place an HTML child at viewBox coordinates inside a W×H box. */
export function At({ x, y, w, h, W, H, children, className }: { x: number; y: number; w: number; h: number; W: number; H: number; children: ReactNode; className?: string }) {
  return (
    <div className={cx("absolute", className)} style={{ left: `${(x / W) * 100}%`, top: `${(y / H) * 100}%`, width: `${(w / W) * 100}%`, height: `${(h / H) * 100}%` }}>
      {children}
    </div>
  );
}

/** A boxed label sitting on a connector ("retry", "not our bug"). */
export function EdgeLabel({ children }: { children: ReactNode }) {
  return <span className="inline-block whitespace-nowrap border border-line-2 bg-surface px-2.5 py-1 font-mono text-[11.5px] leading-none text-t2">{children}</span>;
}

/** A square mono tag. `solid` is the dark, final kind (an output). */
export function Tag({ children, solid }: { children: ReactNode; solid?: boolean }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 border px-2.5 py-1 font-mono text-[11.5px] leading-none",
        solid ? "border-t1 bg-t1 text-surface" : "border-line-2 bg-surface text-t2",
      )}
    >
      {children}
    </span>
  );
}

/** A frame: hairline box with corner brackets. */
function Frame({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("cbox h-full bg-surface", className)}>{children}</div>;
}

function Kicker({ children }: { children: ReactNode }) {
  return <div className="font-mono text-[11px] text-t3">{children}</div>;
}

function Down() {
  return (
    <div aria-hidden className="flex justify-center py-2 font-mono text-[13px] text-t3">
      ↓
    </div>
  );
}

/* ───────────────────────── Fig. 1: signals in, a pull request out ───────────────────────── */

export function HeroDiagram({ run, servers, tools, templates }: { run: FeaturedRun; servers: number; tools: number; templates: number }) {
  const W = 1200;
  const H = 520;
  const signals: [string, string, string[]][] = [
    ["Crash analytics", `A spike in Vitals, like ${run.issue}.`, ["stack", "release", "sessions"]],
    ["Bug reports", "A rider’s report from BugDrop.", ["screenshot", "logs", "device"]],
    ["GitHub issues", "Any issue labeled debugassist.", ["GitHub App", "your repo"]],
  ];
  const mcp = ["crashes", "code search", "git history", "releases", "flags", "logs", "traces", "metrics", "incidents", "Jira", "bug reports"];

  const left = (
    <Frame>
      <div className="flex h-full flex-col">
        {signals.map(([t, d, tags], i) => (
          <div key={t} className={cx("flex-1 px-6 py-5", i > 0 && "border-t border-line")}>
            <h4 className="text-[18px] font-medium tracking-[-0.015em] text-t1">{t}</h4>
            <p className="mt-1 text-[14px] text-t3">{d}</p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {tags.map((g) => (
                <Tag key={g}>{g}</Tag>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Frame>
  );
  const evidence = (
    <Frame>
      <div className="flex h-full flex-col px-6 py-5">
        <h4 className="text-[18px] font-medium tracking-[-0.015em] text-t1">Evidence</h4>
        <p className="mt-1 text-[14px] leading-[1.5] text-t3">
          {servers} MCP servers, {tools} read-only tools. Agents see nothing else.
        </p>
        <div className="mt-4 flex flex-wrap gap-1.5">
          {mcp.map((m) => (
            <Tag key={m}>{m}</Tag>
          ))}
        </div>
      </div>
    </Frame>
  );
  const sandbox = (
    <Frame className="hatch">
      <div className="flex h-full flex-col justify-center px-6 py-5">
        <h4 className="text-[18px] font-medium tracking-[-0.015em] text-t1">
          <span className="bg-surface">Sandbox</span>
        </h4>
        <p className="mt-1 max-w-[30ch] text-[14px] leading-[1.5] text-t3">
          <span className="bg-surface">A container with no network, on a git worktree of the shipped release.</span>
        </p>
      </div>
    </Frame>
  );
  const core = (
    <Frame className="!border-line-strong">
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between px-6 pt-5">
          <h4 className="text-[18px] font-medium tracking-[-0.015em] text-t1">DebugAssist</h4>
          <span className="font-mono text-[11px] text-t3">a fixed plan, in code</span>
        </div>
        <div className="space-y-4 px-6 py-5">
          <Row label="decide">
            <Tag>Clef · {templates} templates</Tag>
            <Tag>policy</Tag>
          </Row>
          <Row label="reason">
            <Tag>root cause</Tag>
            <Tag>reproduce</Tag>
            <Tag>fix</Tag>
          </Row>
          <Row label="act">
            <Tag>evidence</Tag>
            <Tag>tests</Tag>
            <Tag>write gate</Tag>
          </Row>
        </div>
        <div className="mt-auto border-t border-line px-6 py-5">
          <Kicker>out, for {run.issue}</Kicker>
          <div className="mt-3 grid grid-cols-2 gap-1.5">
            {["root cause", "mitigation", "failing test", "draft PR"].map((o) => (
              <Tag key={o} solid>
                {o}
              </Tag>
            ))}
          </div>
          <p className="mt-3 truncate font-mono text-[11px] text-t3">{run.location}</p>
        </div>
      </div>
    </Frame>
  );

  return (
    <div>
      <div className="relative hidden aspect-[1200/520] w-full lg:block">
        <svg viewBox={`0 0 ${W} ${H}`} className="absolute inset-0 h-full w-full overflow-visible" aria-hidden>
          <Defs id="a1" />
          <Edge d="M330 260 H 365 V 150 H 400" arrow="a1" delay={0} />
          <Edge d="M330 260 H 365 V 430 H 400" arrow="a1" delay={0.6} />
          <Edge d="M730 150 H 765 V 260 H 800" arrow="a1" delay={1.2} />
          <Edge d="M730 430 H 765 V 260 H 800" arrow="a1" packet={false} />
          <rect x={362} y={257} width={6} height={6} fill="var(--line-strong)" />
        </svg>
        <At x={0} y={0} w={330} h={520} W={W} H={H}>
          {left}
        </At>
        <At x={400} y={0} w={330} h={300} W={W} H={H}>
          {evidence}
        </At>
        <At x={400} y={340} w={330} h={180} W={W} H={H}>
          {sandbox}
        </At>
        <At x={800} y={0} w={400} h={520} W={W} H={H}>
          {core}
        </At>
      </div>

      <div className="lg:hidden">
        {left}
        <Down />
        {evidence}
        <div className="mt-3">{sandbox}</div>
        <Down />
        {core}
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <Kicker>{label}</Kicker>
      <div className="mt-2 flex flex-wrap gap-1.5">{children}</div>
    </div>
  );
}

/* ───────────────────────── Fig. 4: where a signal goes, and the one way out ───────────────────────── */

export function SystemMap({ servers, tools, templates, branchPrefix }: { servers: number; tools: number; templates: number; branchPrefix: string }) {
  const W = 1200;
  const H = 560;
  const rows = [0, 144, 288, 432];
  const bh = 128;
  const signals: [string, string][] = [
    ["Vitals", "crash analytics"],
    ["BugDrop", "in-app bug reports"],
    ["OpenTelemetry", "traces · logs · metrics"],
    ["GitHub issues", "via the GitHub App"],
  ];
  const writes: [string, string][] = [
    ["Draft pull request", `${branchPrefix}* only`],
    ["Ticket, comment", "Jira · issue thread"],
    ["Chat message", "the on-call channel"],
    ["Flag rollback", "needs approval"],
  ];
  const mid = H / 2;
  const box = (t: string, s: string) => (
    <Frame>
      <div className="flex h-full flex-col justify-center px-5">
        <div className="text-[16px] font-medium tracking-[-0.01em] text-t1">{t}</div>
        <div className="mt-1 font-mono text-[11.5px] text-t3">{s}</div>
      </div>
    </Frame>
  );
  const evidence = (
    <Frame>
      <div className="flex h-full flex-col px-5 py-5">
        <div className="text-[16px] font-medium tracking-[-0.01em] text-t1">MCP servers</div>
        <div className="mt-1 font-mono text-[11.5px] text-t3">
          {servers} servers · {tools} tools
        </div>
        <div className="mt-4 flex flex-wrap gap-1.5">
          {["crash analytics", "bug reports", "code search", "git history", "releases", "feature flags", "logging", "tracing", "metrics", "incidents", "Jira"].map((m) => (
            <Tag key={m}>{m}</Tag>
          ))}
        </div>
        <p className="mt-auto pt-4 text-[13px] leading-[1.5] text-t3">Read-only. The only way an agent sees the world.</p>
      </div>
    </Frame>
  );
  const pipeline = (
    <Frame className="!border-line-strong">
      <div className="flex h-full flex-col px-5 py-5">
        <div className="flex items-baseline justify-between">
          <span className="text-[16px] font-medium tracking-[-0.01em] text-t1">The pipeline</span>
          <span className="font-mono text-[11px] text-t3">LangGraph</span>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-x-1 gap-y-1.5 font-mono text-[11px] text-t2">
          {["ingest", "triage", "context", "root cause", "mitigate", "fix", "validate", "ship gate", "PR", "watch"].map((c, i, a) => (
            <span key={c} className="flex items-center gap-1">
              <span className="border border-line-2 px-1.5 py-0.5">{c}</span>
              {i < a.length - 1 && <span className="text-t4">→</span>}
            </span>
          ))}
        </div>
        <div className="mt-5 grid grid-cols-2 border border-line">
          <div className="p-4">
            <Kicker>Clef</Kicker>
            <div className="mt-2 text-[14px] font-medium text-t1">{templates} decision templates</div>
            <p className="mt-1 text-[12.5px] leading-[1.5] text-t3">A probability, mapped by policy to act, escalate or a safe default.</p>
          </div>
          <div className="border-l border-line p-4">
            <Kicker>Agents</Kicker>
            <div className="mt-2 text-[14px] font-medium text-t1">In a sandbox</div>
            <p className="mt-1 text-[12.5px] leading-[1.5] text-t3">No network, a worktree of the release.</p>
          </div>
        </div>
        <p className="mt-auto pt-4 text-[13px] leading-[1.5] text-t3">
          Models reason inside a step. <span className="text-t1">They never pick the next one.</span>
        </p>
      </div>
    </Frame>
  );
  const gate = (
    <div className="hatch relative h-full border border-line-strong">
      <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 -rotate-90 whitespace-nowrap border border-line-strong bg-surface px-2.5 py-1 font-mono text-[11px] text-t1">
        policy gate · writes.yaml
      </span>
    </div>
  );

  return (
    <div>
      <div className="relative hidden aspect-[1200/560] w-full lg:block">
        <svg viewBox={`0 0 ${W} ${H}`} className="absolute inset-0 h-full w-full overflow-visible" aria-hidden>
          <Defs id="a4" />
          {rows.map((y, i) => (
            <Edge key={`i${y}`} d={`M210 ${y + bh / 2} H 236 V ${mid} H 262`} arrow={i === 0 ? "a4" : undefined} packet={i % 2 === 0} delay={i * 0.5} />
          ))}
          <Edge d={`M542 ${mid} H 590`} arrow="a4" delay={1.4} />
          <Edge d={`M920 ${mid} H 962`} arrow="a4" delay={2} />
          {rows.map((y, i) => (
            <Edge key={`o${y}`} d={`M998 ${mid} H 1012 V ${y + bh / 2} H 1032`} arrow="a4" packet={i === 0 || i === 3} delay={2.6 + i * 0.3} />
          ))}
        </svg>
        {signals.map(([t, s], i) => (
          <At key={t} x={0} y={rows[i]} w={210} h={bh} W={W} H={H}>
            {box(t, s)}
          </At>
        ))}
        <At x={262} y={0} w={280} h={H} W={W} H={H}>
          {evidence}
        </At>
        <At x={590} y={0} w={330} h={H} W={W} H={H}>
          {pipeline}
        </At>
        <At x={962} y={0} w={36} h={H} W={W} H={H}>
          {gate}
        </At>
        {writes.map(([t, s], i) => (
          <At key={t} x={1032} y={rows[i]} w={168} h={bh} W={W} H={H}>
            {box(t, s)}
          </At>
        ))}
      </div>

      <div className="space-y-3 lg:hidden">
        <div className="grid gap-3 sm:grid-cols-2">
          {signals.map(([t, s]) => (
            <div key={t} className="h-[88px]">
              {box(t, s)}
            </div>
          ))}
        </div>
        <Down />
        {evidence}
        <Down />
        {pipeline}
        <Down />
        <div className="hatch border border-line-strong px-4 py-3 text-center font-mono text-[11.5px] text-t1">
          <span className="bg-surface px-2">policy gate · writes.yaml</span>
        </div>
        <Down />
        <div className="grid gap-3 sm:grid-cols-2">
          {writes.map(([t, s]) => (
            <div key={t} className="h-[88px]">
              {box(t, s)}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ───────────────────────── The principle: decide, reason, act ───────────────────────── */

export function Principle({ templates }: { templates: number }) {
  return (
    <div className="grid gap-3 lg:grid-cols-3">
      <PCard
        tag="Clef decides"
        title="Every judgement call is a probability."
        body={`Priority, rollback, test tier, ship — ${templates} decision templates, each mapped by policy to act, escalate or a safe default.`}
      >
        <div className="w-full max-w-[300px] font-mono text-[11.5px]">
          <div className="flex justify-between text-t3">
            <span>roll back the flag?</span>
            <span className="text-t1">p = 0.02</span>
          </div>
          <div className="relative mt-3 h-3 border border-line-2 bg-surface">
            <div className="absolute inset-y-0 left-0 w-[6%] bg-t1" />
            <div className="absolute -bottom-2 -top-2 left-[74%] w-px bg-t1" />
            <span className="absolute -top-6 left-[74%] -translate-x-1/2 text-t2">τ</span>
          </div>
          <div className="mt-4 inline-block border border-t1 bg-t1 px-2.5 py-1.5 text-surface">→ safe default: no rollback</div>
        </div>
      </PCard>
      <PCard
        tag="Agents reason"
        title="Models read evidence and write code."
        body="Inside one step, in a sandbox with no network. They explain and fix. They never choose what happens next."
      >
        <div className="w-full max-w-[320px] overflow-hidden whitespace-pre border border-line-2 bg-surface font-mono text-[11px] leading-[1.8]">
          <div className="border-b border-line px-3 py-1.5 text-t3">router.ts · the fix for VIT-1001</div>
          <div className="px-3 pt-1.5 text-t3">async function routeV2(…) {"{"}</div>
          <div className="bg-sunk px-3 text-t1">{"+   await whenHydrated();"}</div>
          <div className="px-3 text-t2">{"    const state = sessionStore.getState();"}</div>
          <div className="px-3 pb-1.5 text-t3">{"}"}</div>
        </div>
      </PCard>
      <PCard
        tag="Code acts"
        title="Every write goes through one gate."
        body="Deterministic steps gather evidence, run the tests and perform each write — through a policy file, into an audit log."
      >
        <div className="flex w-full max-w-[300px] flex-col font-mono text-[11.5px]">
          {["context_collector", "validate"].map((s) => (
            <div key={s} className="-mb-px flex items-center justify-between border border-line-2 bg-surface px-3 py-2 text-t2">
              {s}
              <span className="text-t3">passed</span>
            </div>
          ))}
          <div className="mt-3 flex items-center justify-between border border-t1 bg-t1 px-3 py-2 text-surface">
            policy gate
            <span>→ draft PR</span>
          </div>
        </div>
      </PCard>
    </div>
  );
}

function PCard({ tag, title, body, children }: { tag: string; title: string; body: string; children: ReactNode }) {
  return (
    <div className="fx flex flex-col border border-line bg-surface">
      <div className="p-7">
        <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-t3">{tag}</div>
        <h3 className="title mt-4 text-[24px] text-t1">{title}</h3>
        <p className="mt-2.5 text-[15px] leading-[1.6] text-t3">{body}</p>
      </div>
      <div className="grid-paper mt-auto grid min-h-[210px] place-items-center border-t border-line px-6 py-8">{children}</div>
    </div>
  );
}
