import type { ReactNode } from "react";

// Feature cards: a title, one sentence, and a small line drawing on an isometric plane.
function Plane({ children, wide }: { children: ReactNode; wide?: boolean }) {
  return (
    <div
      className={`drafting relative h-[220px] overflow-hidden border-line ${
        wide ? "border-t md:h-full md:min-h-[250px] md:border-l md:border-t-0" : "mt-5 border-t"
      }`}
    >
      <div
        className="absolute left-1/2 top-1/2 w-[236px]"
        style={{ transform: "translate(-50%, -50%) rotate(-30deg) skewX(30deg) scaleY(0.864) scale(0.92)" }}
      >
        {/* on hover the drawing lifts off the plane */}
        <div className="transition-transform duration-500 ease-[cubic-bezier(.2,.8,.2,1)] group-hover:-translate-x-2 group-hover:-translate-y-3">
          {children}
        </div>
      </div>
    </div>
  );
}

const slab =
  "border border-[#2f2e2a] bg-[#fdfdfb] px-3 py-2 font-mono text-[11px] text-[#2f2e2a] shadow-[3px_3px_0_0_#d9d8d1]";

const FEATURES: { title: string; body: string; art: ReactNode }[] = [
  {
    title: "Evidence-backed root cause",
    body: "Every claim cites the evidence it rests on, and each claim is checked against that evidence before anyone reads it.",
    art: (
      <div className="space-y-2.5">
        <div className={slab}>routeV2 skips await whenHydrated()</div>
        <div className="ml-8 space-y-1.5 font-mono text-[10px]">
          <div className="text-[#3f8f4f]">✓ ev_code · grounded</div>
          <div className="text-[#3f8f4f]">✓ ev_flags · grounded</div>
          <div className="text-[#c9443a]">✗ ev_logs · dropped</div>
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
          <span className="text-[#c9443a]">✗</span>
        </div>
        <div className={`${slab} ml-5 flex justify-between`}>
          <span>passes with fix</span>
          <span className="text-[#3f8f4f]">✓</span>
        </div>
        <div className={`${slab} ml-10 flex justify-between`}>
          <span>suite · lint · CI</span>
          <span className="text-[#3f8f4f]">✓</span>
        </div>
      </div>
    ),
  },
  {
    title: "Clef decides, calibrated",
    body: "Priority, category, rollback, test tier, retry, ship: decision templates on Cloudflare Clef, mapped by policy to act, escalate or a safe default.",
    art: (
      <div className="space-y-3">
        <div className={slab}>D11 · roll back the flag?</div>
        <div className="relative h-3 border border-[#2f2e2a] bg-[#fdfdfb]">
          <div className="absolute inset-y-0 left-0 w-[86%] bg-[#f6f87e]" />
          <div className="absolute -top-1.5 -bottom-1.5 left-[74%] border-l-[1.5px] border-[#2f2e2a]" />
        </div>
        <div className="flex justify-between font-mono text-[10px] text-[#6b6b66]">
          <span>calibrated p</span>
          <span>p ≥ τ → act</span>
        </div>
      </div>
    ),
  },
  {
    title: "Sandboxed and policy-gated",
    body: "Agents work in a network-less container on a git worktree. Every write — PR, ticket, flag — passes a policy gate and an audit log.",
    art: (
      <div className="grid grid-cols-2 gap-2.5">
        <div className={slab}>--network none</div>
        <div className={slab}>git worktree</div>
        <div className={`${slab} col-span-2 bg-[#f6f87e]`}>policy gate · bot branches only</div>
        <div className={slab}>dry-run</div>
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
            <div className={`${slab} ${s === "rca" || s === "fix" ? "!border-[#8b7cf0]" : ""}`}>{s}</div>
            {i < 4 && <span className="text-[#6b6b66]">→</span>}
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
];

// Bento: wide cards put the drawing beside the text.
const WIDE = new Set([0, 3, 5]);

export function Features() {
  return (
    <div className="grid gap-2 md:grid-cols-3">
      {FEATURES.map((f, i) => {
        const wide = WIDE.has(i);
        return (
          <div
            key={f.title}
            className={`group cbox spot fx flex flex-col overflow-hidden ${wide ? "md:col-span-2 md:grid md:grid-cols-2" : ""}`}
            style={{ ["--i" as string]: i % 2 }}
          >
            <div className={`px-6 pt-6 ${wide ? "md:flex md:flex-col md:justify-between md:pb-6" : ""}`}>
              <div>
                <div className="font-mono text-[10.5px] uppercase tracking-[0.06em] text-t4">{String(i + 1).padStart(2, "0")}</div>
                <h3 className="mt-2 font-display text-[21px] font-medium tracking-[-0.02em] text-t1">{f.title}</h3>
                <p className="mt-2 max-w-[44ch] text-[14.5px] leading-[1.55] text-t3">{f.body}</p>
              </div>
            </div>
            <div className="mt-auto md:h-full">
              <Plane wide={wide}>{f.art}</Plane>
            </div>
          </div>
        );
      })}
    </div>
  );
}
