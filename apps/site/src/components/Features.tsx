import type { ReactNode } from "react";

// Feature cards with small line illustrations drawn on an isometric plane (CSS 3D transform).
function Plane({ children }: { children: ReactNode }) {
  return (
    <div className="relative h-52 overflow-hidden mt-4 -mx-5 -mb-5 border-t border-line-2">
      <div
        className="absolute left-1/2 top-1/2 w-[300px] origin-center"
        style={{ transform: "translate(-50%, -50%) rotate(-30deg) skewX(30deg) scaleY(0.864)" }}
      >
        {children}
      </div>
    </div>
  );
}

const chip = "font-mono text-[11px] border border-ink-2 bg-panel px-2.5 py-1.5 shadow-[3px_3px_0_0_var(--line)]";

const FEATURES: { title: string; body: string; art: ReactNode }[] = [
  {
    title: "Evidence-backed root cause",
    body: "Every claim in the RCA cites the evidence id it rests on, and each claim is checked against that evidence before anyone sees it.",
    art: (
      <div className="space-y-2">
        <div className={chip}>routeV2 skips await whenHydrated()</div>
        <div className="ml-10 space-y-1.5">
          <div className="font-mono text-[10px] text-muted">ev_code_3f2a91c0d1 · ✓ grounded</div>
          <div className="font-mono text-[10px] text-muted">ev_flags_9b1e22a7c4 · ✓ grounded</div>
          <div className="font-mono text-[10px] text-bad">ev_logs_00e1f3b2aa · ✗ dropped</div>
        </div>
      </div>
    ),
  },
  {
    title: "Proof before a pull request",
    body: "A test that fails on the shipped release, a fix that makes it pass, the suite and the repo's own CI green. No proof, no ready PR.",
    art: (
      <div className="space-y-2">
        <div className={`${chip} flex justify-between`}>
          <span>fails on release</span>
          <span className="text-bad">exit 1</span>
        </div>
        <div className={`${chip} flex justify-between ml-6`}>
          <span>passes with fix</span>
          <span className="text-good">exit 0</span>
        </div>
        <div className={`${chip} flex justify-between ml-12`}>
          <span>suite · lint · typecheck</span>
          <span className="text-good">green</span>
        </div>
      </div>
    ),
  },
  {
    title: "Clef decides, with calibrated confidence",
    body: "Priority, category, rollback, test tier, retry, ship — 18 decision templates on Cloudflare Clef, mapped to act / escalate / safe default by policy.",
    art: (
      <div className="space-y-3">
        <div className={chip}>D11 · roll back notif_router_v2?</div>
        <div className="relative h-3 border border-ink-2 bg-panel">
          <div className="absolute inset-y-0 left-0 bg-mark" style={{ width: "91%" }} />
          <div className="absolute inset-y-[-6px] border-l-2 border-ink-2" style={{ left: "80%" }} />
        </div>
        <div className="flex justify-between font-mono text-[10px] text-muted">
          <span>calibrated p</span>
          <span>p ≥ τ → act · else escalate</span>
        </div>
      </div>
    ),
  },
  {
    title: "Sandboxed, policy-gated, audited",
    body: "Agents work in a network-less container on a git worktree. Every write — PR, ticket, flag — goes through a policy gate and an audit log.",
    art: (
      <div className="grid grid-cols-2 gap-3">
        <div className={chip}>docker --network none</div>
        <div className={chip}>git worktree</div>
        <div className={`${chip} col-span-2 text-center`}>policy gate: debugassist/* branches only</div>
        <div className={`${chip} text-center`}>dry-run</div>
        <div className={`${chip} text-center`}>audit log</div>
      </div>
    ),
  },
  {
    title: "Watch every run live",
    body: "A dashboard draws each run as its fixed graph, with every model call, tool call and Clef decision, its cost and its latency.",
    art: (
      <div className="flex items-center gap-2 flex-wrap">
        {["ingest", "triage", "rca", "fix", "validate"].map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <div className={`${chip} ${s === "rca" || s === "fix" ? "border-[#7c6be6]" : ""}`}>{s}</div>
            {i < 4 && <span className="text-muted">→</span>}
          </div>
        ))}
        <div className="w-full font-mono text-[10px] text-muted mt-1">cost · time · turns · decisions, per step</div>
      </div>
    ),
  },
  {
    title: "A harness, not a prompt",
    body: "Agent types per kind of issue, five plugins of skills loaded on demand, domain knowledge bases, and a PEX + runtime image per agent type.",
    art: (
      <div className="relative h-44">
        {["perf-and-battery", "backend-fixes", "web-client-fixes", "test-planning", "pr-authoring"].map((s, i) => (
          <div key={s} className={`${chip} absolute`} style={{ left: 30 + i * 22, top: i * 30 }}>
            {s}
          </div>
        ))}
      </div>
    ),
  },
];

export function Features() {
  return (
    <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
      {FEATURES.map((f) => (
        <div key={f.title} className="frame p-5 overflow-hidden">
          <span className="frame-corners" />
          <h3 className="text-xl font-medium">{f.title}</h3>
          <p className="mt-2 text-ink-2 leading-relaxed">{f.body}</p>
          <Plane>{f.art}</Plane>
        </div>
      ))}
    </div>
  );
}
