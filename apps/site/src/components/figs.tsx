import Link from "next/link";
import type { ReactNode } from "react";
import { Draw } from "@/components/Draw";
import type { DecisionMetrics, WriteRule } from "@/lib/data";
import type { Adr, Lesson } from "@/lib/docs";

// The chapter pages' figures. Each draws something the repository states — a doc, a config or a report — and says
// where; nothing here is decorative.

// ───────────────────────── Discovery ─────────────────────────

/** Vitals: from one crash event to an issue (docs/ARCHITECTURE.md › Discovery sources). */
export function FingerprintFlow() {
  return (
    <Draw
      w={1200}
      h={300}
      boxes={[
        { x: 0, y: 95, w: 200, h: 110, title: "Crash event", tag: "SDK", lines: ["stack · version", "device · city · flags"] },
        { x: 250, y: 95, w: 210, h: 110, title: "Normalize", lines: ["in-app frames only", "no line numbers", "no asset hashes"] },
        { x: 510, y: 95, w: 180, h: 110, title: "Fingerprint", lines: ["one key per bug,", "across builds"] },
        { x: 740, y: 95, w: 200, h: 110, title: "Group", lines: ["count · first / last version", "sessions as denominator"] },
        { x: 990, y: 20, w: 210, h: 100, title: "Open an issue", tag: "VIT-…", lines: ["a group seen", "for the first time"], tone: "ink" },
        { x: 990, y: 180, w: 210, h: 100, title: "Reopen it", tag: "regression", lines: ["the group comes back", "on a newer version"] },
      ]}
      edges={[
        { d: "M200 150 H 250" },
        { d: "M460 150 H 510" },
        { d: "M690 150 H 740" },
        { d: "M940 150 H 965 V 70 H 990" },
        { d: "M940 150 H 965 V 230 H 990" },
      ]}
      labels={[{ x: 355, y: 232, text: "source maps → function names", boxed: false }]}
      steps={[
        "A crash event arrives with its stack, version, device, city and flag exposures.",
        "The stack is normalized: in-app frames only, without line numbers or asset hashes; source maps restore function names.",
        "The normalized stack is fingerprinted, so one bug is one group across builds.",
        "Events join their group, which keeps counts, first and last version, and session denominators.",
        "A new group opens a Vitals issue; a group seen again on a newer version reopens its issue as a regression.",
      ]}
    />
  );
}

// ───────────────────────── Decisions ─────────────────────────

/** D12's two-stage choice for large candidate sets (docs/decisions.md › Two-stage). */
export function TwoStage({ act, escalate, safe }: { act: string[]; escalate: string; safe: string }) {
  return (
    <Draw
      w={1200}
      h={330}
      boxes={[
        { x: 0, y: 105, w: 180, h: 120, title: "Candidates", tag: "N", lines: ["files and functions", "from code search"] },
        { x: 230, y: 105, w: 240, h: 120, title: "One noul each", tag: "stage 1", lines: ["is this the location?", "chunks of 64, concurrent"] },
        { x: 520, y: 105, w: 150, h: 120, title: "Top K", lines: ["highest P(yes)"] },
        { x: 720, y: 105, w: 190, h: 120, title: "One choice", tag: "stage 2", lines: ["over the top K", "plus none"], tone: "ink" },
        { x: 960, y: 10, w: 240, h: 95, title: "act", lines: act },
        { x: 960, y: 125, w: 240, h: 80, title: "escalate", lines: [escalate] },
        { x: 960, y: 225, w: 240, h: 80, title: "safe default", lines: [safe], tone: "hatch" },
      ]}
      edges={[
        { d: "M180 165 H 230" },
        { d: "M470 165 H 520" },
        { d: "M670 165 H 720" },
        { d: "M910 165 H 935 V 57 H 960" },
        { d: "M910 165 H 960" },
        { d: "M910 165 H 935 V 265 H 960" },
      ]}
      labels={[{ x: 90, y: 70, text: "only when N > max_direct" }]}
      steps={[
        "With more candidates than max_direct, D12 does not ask one huge question.",
        "Stage 1: one yes/no question per candidate — is this the location? — sent in chunks of 64, concurrently.",
        "The K candidates with the highest P(yes) are kept.",
        "Stage 2: a single choice over those K, plus none.",
        `The policy band maps it: act → ${act.join("; ")}; escalate → ${escalate}; safe default → ${safe}.`,
      ]}
    />
  );
}

// ───────────────────────── Why Clef ─────────────────────────

/** The four backends behind one request type (docs/decisions.md › Backends). */
export function Backends() {
  return (
    <Draw
      w={1200}
      h={320}
      boxes={[
        { x: 0, y: 110, w: 190, h: 100, title: "ClefRequest", lines: ["template · state", "params · images"] },
        { x: 270, y: 10, w: 270, h: 90, title: "WorkersAIClef", tag: "default", lines: ["Clef / Clef-flash · keys set", "retries 429 · 5xx · timeouts"], tone: "ink" },
        { x: 270, y: 115, w: 270, h: 90, title: "LLMDecider", tag: "fallback", lines: ["breaker open · baseline", "escalation second opinion"] },
        { x: 270, y: 220, w: 270, h: 90, title: "MockDecider", tag: "CI", lines: ["no keys · demos", "deterministic per question"], tone: "dashed" },
        { x: 640, y: 110, w: 220, h: 100, title: "Policy band", lines: ["act · escalate", "safe default"] },
        { x: 930, y: 110, w: 270, h: 100, title: "Decision ledger", lines: ["state hash · answers · band", "action · cost · mode"], tone: "sunk" },
      ]}
      edges={[
        { d: "M190 160 H 230 V 55 H 270" },
        { d: "M190 160 H 270" },
        { d: "M190 160 H 230 V 265 H 270", dashed: true },
        { d: "M540 55 H 600 V 150 H 640" },
        { d: "M540 160 H 640" },
        { d: "M540 265 H 600 V 170 H 640", dashed: true },
        { d: "M860 160 H 930" },
      ]}
      labels={[{ x: 405, y: 107, text: "circuit breaker", boxed: true }]}
      steps={[
        "Every decision is one ClefRequest: a template, the state, parameters and optional images.",
        "WorkersAIClef answers it when Cloudflare keys are set, retrying rate limits, server errors and timeouts.",
        "If its circuit breaker opens, the LLMDecider answers instead — also the baseline and the escalation second opinion.",
        "Without keys (CI, demos) the MockDecider answers deterministically.",
        "Whichever answered, the policy band maps the probability to an action, and the decision ledger records it.",
      ]}
    />
  );
}

/** Coverage at τ_high against accuracy: what abstaining buys (decisions.csv). */
export function Abstain({ rows, name }: { rows: DecisionMetrics[]; name: (d: string) => string }) {
  const W = 1000;
  const H = 440;
  const L = 70;
  const R = 30;
  const T = 20;
  const B = 50;
  const x = (v: number) => L + v * (W - L - R);
  const y = (v: number) => T + (1 - v) * (H - T - B);
  const pts = rows.filter((r) => r.coverage !== null && r.accuracyAtTau !== null);
  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} className="hidden w-full sm:block" role="img" aria-label="Coverage at tau high against accuracy, per decision">
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={T} y2={H - B} stroke="var(--line)" />
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="var(--line)" />
            <text x={x(t)} y={H - B + 20} textAnchor="middle" fontSize="11" fontFamily="var(--font-mono)" fill="var(--fg-3)">
              {Math.round(t * 100)}%
            </text>
            <text x={L - 10} y={y(t) + 4} textAnchor="end" fontSize="11" fontFamily="var(--font-mono)" fill="var(--fg-3)">
              {Math.round(t * 100)}%
            </text>
          </g>
        ))}
        <text x={(L + W - R) / 2} y={H - 8} textAnchor="middle" fontSize="11" fontFamily="var(--font-mono)" fill="var(--fg-2)">
          acts on this share of its decisions (p ≥ τ_high) →
        </text>
        <text x={16} y={(T + H - B) / 2} textAnchor="middle" fontSize="11" fontFamily="var(--font-mono)" fill="var(--fg-2)" transform={`rotate(-90 16 ${(T + H - B) / 2})`}>
          accuracy →
        </text>
        <text x={x(0.02)} y={y(0.98)} fontSize="11" fontFamily="var(--font-mono)" fill="var(--fg-4)">
          abstains, right when it acts
        </text>
        <text x={x(0.98)} y={y(0.04)} textAnchor="end" fontSize="11" fontFamily="var(--font-mono)" fill="var(--fg-4)">
          acts on everything, often wrong
        </text>
        {pts.map((r) => {
          const cx = x(r.coverage!);
          const left = r.coverage! > 0.75;
          return (
            <g key={r.decision}>
              <line x1={cx} x2={cx} y1={y(r.accuracy)} y2={y(r.accuracyAtTau!)} stroke="var(--fg)" strokeDasharray="3 3" />
              <rect x={cx - 5} y={y(r.accuracy) - 5} width={10} height={10} fill="var(--raised)" stroke="var(--fg)" />
              <rect x={cx - 6} y={y(r.accuracyAtTau!) - 6} width={12} height={12} fill="var(--fg)" />
              <text x={left ? cx - 14 : cx + 14} y={y(r.accuracyAtTau!) + 4} textAnchor={left ? "end" : "start"} fontSize="12" fontFamily="var(--font-mono)" fill="var(--fg)">
                {r.decision.slice(0, 3)} {name(r.decision)}
              </text>
            </g>
          );
        })}
      </svg>
      <ul className="grid gap-2 sm:hidden">
        {pts.map((r) => (
          <li key={r.decision} className="border border-line bg-surface p-3 font-mono text-[12px] text-t2">
            {r.decision.slice(0, 3)} {name(r.decision)}: acts on {Math.round(r.coverage! * 100)}%, right {Math.round(r.accuracyAtTau! * 100)}% when it acts ·{" "}
            {Math.round(r.accuracy * 100)}% overall
          </li>
        ))}
      </ul>
      <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 font-mono text-[11px] text-t3">
        <span className="inline-flex items-center gap-2">
          <i className="inline-block h-3 w-3 bg-t1" /> accuracy when it acts
        </span>
        <span className="inline-flex items-center gap-2">
          <i className="inline-block h-2.5 w-2.5 border border-t1 bg-surface" /> accuracy overall
        </span>
        <span>dashed: what abstaining buys</span>
      </div>
    </>
  );
}

// ───────────────────────── Safety ─────────────────────────

/** Where untrusted input crosses a boundary, and what holds each one (docs/THREAT-MODEL.md › Boundaries). */
export function TrustBoundaries() {
  const zone = (x: number) => <line key={x} x1={x} x2={x} y1={70} y2={330} stroke="var(--fg)" strokeDasharray="6 5" />;
  return (
    <Draw
      w={1200}
      h={400}
      svg={[210, 465, 735, 985].map(zone)}
      boxes={[
        { x: 0, y: 145, w: 170, h: 120, title: "Strangers' text", lines: ["issue bodies · logs", "commits · test output"], tone: "hatch" },
        { x: 250, y: 145, w: 175, h: 120, title: "Model", lines: ["follows instructions", "it should not"] },
        { x: 505, y: 145, w: 190, h: 120, title: "Container", lines: ["--network none", "--cap-drop ALL", ".git read-only"] },
        { x: 775, y: 145, w: 170, h: 120, title: "Host", lines: ["git · grep · walks", "keys in .env"] },
        { x: 1025, y: 145, w: 175, h: 120, title: "Outside world", lines: ["repos · tracker", "chat · flags"], tone: "ink" },
      ]}
      edges={[{ d: "M170 205 H 250" }, { d: "M425 205 H 505" }, { d: "M695 205 H 775" }, { d: "M945 205 H 1025" }]}
      labels={[
        { x: 210, y: 40, text: "fenced as <untrusted_data>" },
        { x: 465, y: 40, text: "commands run in the container" },
        { x: 735, y: 40, text: "core.hostgit · no symlinks" },
        { x: 985, y: 40, text: "one policy gate · audit" },
        { x: 210, y: 360, text: "test_injection.py", boxed: false },
        { x: 465, y: 360, text: "test_hostgit.py", boxed: false },
        { x: 735, y: 360, text: "test_workspace_tools.py", boxed: false },
        { x: 985, y: 360, text: "test_gated_writes.py", boxed: false },
      ]}
      steps={[
        "Text strangers write — issue bodies, logs, commit messages — reaches the model fenced as <untrusted_data>, never as instruction.",
        "The model's commands run only in a container with no network, no capabilities and a read-only .git.",
        "What the container writes is hostile to the host: host git uses a verified git dir with hooks off, and walks never follow symlinks.",
        "Anything that leaves for repositories, trackers, chat or flags passes one policy gate and the audit log.",
      ]}
    />
  );
}

// The modes, as configs/policies/writes.yaml's header defines them.
const MODES: [string, string, string[]][] = [
  ["live", "live", ["performed, and audited"]],
  ["approval", "approval", ["supervised runs wait for a human", "autonomous runs dry-run"]],
  ["dry_run", "dry run", ["recorded, not performed", "the default for anything unlisted"]],
  ["deny", "deny", ["never performed"]],
];

/** One write through the gate: the mode writes.yaml gives it, with the number of actions listed under each. */
export function WriteGate({ rules }: { rules: WriteRule[] }) {
  const count = (m: string) => rules.filter((r) => r.mode === m).length;
  const tag = (m: string) => (count(m) ? `${count(m)} listed` : "none listed");
  const ys = [0, 92, 184, 276];
  return (
    <Draw
      w={1200}
      h={364}
      boxes={[
        { x: 0, y: 135, w: 190, h: 95, title: "A write", lines: ["push · comment · PR", "ticket · flag · chat"] },
        { x: 250, y: 135, w: 230, h: 95, title: "writes.yaml", tag: `${rules.length} actions`, lines: ["listed? which mode?"], tone: "ink" },
        ...MODES.map(([m, t, lines], i) => ({
          x: 560,
          y: ys[i],
          w: 300,
          h: 86,
          title: t,
          tag: tag(m),
          lines,
          tone: (m === "deny" ? "hatch" : m === "dry_run" ? "dashed" : "plain") as "hatch" | "dashed" | "plain",
        })),
        { x: 940, y: 0, w: 260, h: 168, title: "Audit log", lines: ["what was applied", ".data/audit.jsonl"], tone: "sunk" },
      ]}
      edges={[
        { d: "M190 182 H 250" },
        ...ys.map((y) => ({ d: `M480 182 H 520 V ${y + 43} H 560` })),
        { d: "M860 43 H 940" },
        { d: "M860 135 H 940" },
      ]}
      steps={[
        "Every side effect — a push, a comment, a pull request, a ticket, a flag change, a chat message — is an action.",
        `configs/policies/writes.yaml gives each of its ${rules.length} listed actions a mode.`,
        ...MODES.map(([m, t, lines]) => `${t} (${tag(m)}): ${lines.join("; ")}.`),
        "What is applied is written to the audit log.",
      ]}
    />
  );
}

// ───────────────────────── Test bed ─────────────────────────

/** How one catalog bug is shipped, as a git graph (docs/ARCHITECTURE.md › Bug catalog and scenarios). */
export function ShipGraph() {
  const sq = (x: number, y: number, ink = true) => <rect key={`${x}-${y}`} x={x - 7} y={y - 7} width={14} height={14} fill={ink ? "var(--fg)" : "var(--raised)"} stroke="var(--fg)" />;
  return (
    <Draw
      w={1200}
      h={330}
      svg={
        <>
          <line x1={20} x2={1180} y1={70} y2={70} stroke="var(--fg)" strokeWidth={1.5} />
          <path d="M300 70 V 190 H 820" fill="none" stroke="var(--fg)" strokeWidth={1.5} />
          <path d="M820 190 H 860" fill="none" stroke="var(--fg)" strokeWidth={1.5} strokeDasharray="4 4" />
          {[120, 300, 1060].map((x) => sq(x, 70, x === 300))}
          {sq(520, 190)}
          {sq(760, 190, false)}
        </>
      }
      boxes={[{ x: 880, y: 140, w: 320, h: 170, title: "Then, on the live stack", lines: ["rebuild the affected services", "previous client keeps a share on :8081", "flag rollout · Toxiproxy · incident", "rider fleet + Locust traffic", "→ found by Vitals or BugDrop"], tone: "plain" }]}
      labels={[
        { x: 20, y: 40, text: "main", boxed: false, anchor: "l" },
        { x: 300, y: 40, text: "base tag" },
        { x: 230, y: 190, text: "release/<version>", boxed: false, anchor: "r" },
        { x: 520, y: 228, text: "regression · git am" },
        { x: 520, y: 260, text: "a fictional MiniRide author", boxed: false },
        { x: 760, y: 228, text: "release.sh · v1.6.x" },
        { x: 1060, y: 40, text: "reset restores main" },
      ]}
      steps={[
        "A release/<version> branch is cut from the base tag on main.",
        "The regression is applied with git am, authored by a fictional MiniRide engineer.",
        "The repository's own release.sh tags it v1.6.x.",
        "On the live stack: the affected services rebuild, the previous client keeps a share of sessions, flags, toxics and incidents are applied, and rider traffic runs — until Vitals or BugDrop finds it.",
        "reset restores main, baseline flags and a clean environment.",
      ]}
    />
  );
}

// ───────────────────────── On your repository ─────────────────────────

/** The GitHub App, end to end, as a sequence (docs/github-app.md). */
export function AppSequence() {
  const lanes = [
    { x: 110, t: "Maintainer" },
    { x: 420, t: "GitHub" },
    { x: 760, t: "DebugAssist (host)" },
    { x: 1070, t: "Sandbox" },
  ];
  const msgs: [number, number, string, boolean?][] = [
    [0, 1, "labels the issue debugassist"],
    [1, 2, "poll (or a signed webhook) picks it up"],
    [2, 1, "clone the default branch · token on the host"],
    [2, 3, "pipeline, no network"],
    [3, 2, "root cause · failing test · fix · proof", true],
    [2, 1, "comment the root cause on the issue"],
    [2, 1, "push debugassist/* · open a draft PR"],
    [1, 0, "a draft to review", true],
  ];
  const y0 = 110;
  const dy = 42;
  return (
    <Draw
      w={1200}
      h={y0 + msgs.length * dy + 20}
      svg={lanes.map((l) => (
        <line key={l.x} x1={l.x} x2={l.x} y1={64} y2={y0 + msgs.length * dy} stroke="var(--line-2)" strokeDasharray="4 4" />
      ))}
      boxes={lanes.map((l, i) => ({ x: l.x - 110, y: 10, w: 220, h: 54, title: l.t, tone: i === 2 ? ("ink" as const) : ("plain" as const) }))}
      edges={msgs.map(([a, b, , back], i) => ({ d: `M${lanes[a].x} ${y0 + i * dy} H ${lanes[b].x + (b > a ? -4 : 4)}`, dashed: back }))}
      labels={msgs.map(([a, b, t], i) => ({ x: (lanes[a].x + lanes[b].x) / 2, y: y0 + i * dy - 11, text: t, boxed: false }))}
      steps={msgs.map(([a, b, t]) => `${lanes[a].t} → ${lanes[b].t}: ${t}.`)}
    />
  );
}

/** What the App may and may never touch (docs/github-app.md › What it may do). */
export function AppScope() {
  return (
    <Draw
      w={1200}
      h={330}
      boxes={[
        { x: 0, y: 20, w: 330, h: 290, title: "May", lines: ["comment on the labeled issue", "push debugassist/* branches", "open pull requests — as drafts", "only on installed repositories", "only with .DebugAssist/pipeline.yaml", "every write through the gate and audit"] },
        { x: 435, y: 105, w: 330, h: 120, title: "The App", tag: "installation", lines: ["installing it is the opt-in", "uninstalling takes the repo away"], tone: "ink" },
        { x: 870, y: 20, w: 330, h: 290, title: "Never", lines: ["the default branch", "release/* branches", "tags", "repositories it is not installed on", "anything, if its API is unreachable", "a token inside the sandbox"], tone: "hatch" },
      ]}
      edges={[{ d: "M435 165 H 330" }, { d: "M765 165 H 870", dashed: true }]}
      labels={[{ x: 600, y: 270, text: "tokens live an hour, on the host only" }]}
      steps={[
        "Installing the App on a repository is the opt-in; uninstalling it takes the repository away.",
        "It may comment on the labeled issue, push debugassist/* branches and open draft pull requests — on installed repositories that carry .DebugAssist/pipeline.yaml, every write through the gate.",
        "It never touches the default branch, release/* or tags, repositories it is not installed on, or anything if its API is unreachable.",
        "Installation tokens live an hour and are used on the host only — never in the sandbox.",
      ]}
    />
  );
}

// ───────────────────────── Design records ─────────────────────────

// Which part of the system each record governs, outside in — read from each ADR's own title.
const LAYERS: [string, string, string[]][] = [
  ["Outside world", "repositories · trackers · chat", ["0008"]],
  ["Host", "what it trusts, how it runs", ["0009", "0010"]],
  ["Pipeline", "the graph and its nodes", ["0001"]],
  ["Decisions", "judgement calls", ["0002"]],
  ["Evidence", "what the agent is shown", ["0003"]],
  ["Models", "how LLM calls are made", ["0004", "0007"]],
  ["Foundations", "workspace · test bed", ["0005", "0006"]],
];

// A record's title, without its parenthetical, and cut at the first comma when it is long.
const short = (t: string) => {
  const s = t.replace(/\s*\(.*\)$/, "").replace(/`/g, "");
  return s.length > 60 ? s.split(",")[0] : s;
};

/** The system as layers, outside in, each with the records that govern it. */
export function AdrLayers({ records }: { records: Adr[] }) {
  const rowH = 76;
  const gap = 10;
  const by = (n: string) => records.find((r) => r.n === n);
  return (
    <Draw
      w={1200}
      h={LAYERS.length * (rowH + gap) - gap}
      boxes={LAYERS.map(([t, what, ns], i) => ({
        x: i * 14,
        y: i * (rowH + gap),
        w: 1200 - i * 28,
        h: rowH,
        title: t,
        tag: ns.map((n) => `ADR ${n}`).join(" · "),
        lines: [
          <span key="l">
            {what} —{" "}
            {ns.map((n, j) => {
              const r = by(n);
              return (
                r && (
                  <span key={n}>
                    {j > 0 && " · "}
                    <Link href={`/design/${r.slug}/`} className="text-current underline decoration-current/40 underline-offset-2 hover:decoration-current">
                      {short(r.title)}
                    </Link>
                  </span>
                )
              );
            })}
          </span>,
        ],
        tone: (i === 0 ? "ink" : i === LAYERS.length - 1 ? "sunk" : "plain") as "ink" | "sunk" | "plain",
      }))}
      steps={LAYERS.map(([t, what, ns]) => (
        <>
          <b className="font-medium text-t1">{t}</b> — {what}:{" "}
          {ns
            .map(by)
            .filter((r): r is Adr => !!r)
            .map((r) => `ADR ${r.n} ${r.title.replace(/`/g, "")}`)
            .join("; ")}
        </>
      ))}
    />
  );
}

/** One record's three parts (docs/adr/0000-template.md) and where the records stand. */
export function AdrAnatomy({ records }: { records: Adr[] }) {
  const n = (p: string) => records.filter((r) => r.status.startsWith(p)).length;
  return (
    <Draw
      w={1200}
      h={300}
      boxes={[
        { x: 0, y: 20, w: 320, h: 120, title: "Context", lines: ["what forced a choice:", "a constraint, a failure, a cost"] },
        { x: 440, y: 20, w: 320, h: 120, title: "Decision", lines: ["what is decided, in one place", "the code cites it"], tone: "ink" },
        { x: 880, y: 20, w: 320, h: 120, title: "Consequences", lines: ["what it costs, and what", "it rules out"] },
        { x: 0, y: 200, w: 320, h: 80, title: "proposed", tag: `${n("proposed")}`, tone: "dashed" },
        { x: 440, y: 200, w: 320, h: 80, title: "accepted", tag: `${n("accepted")}` },
        { x: 880, y: 200, w: 320, h: 80, title: "superseded by NNNN", tag: `${n("superseded")}`, tone: "hatch" },
      ]}
      edges={[{ d: "M320 80 H 440" }, { d: "M760 80 H 880" }, { d: "M320 240 H 440" }, { d: "M760 240 H 880", dashed: true }]}
      labels={[{ x: 600, y: 170, text: "status · and how many records hold it" }]}
      steps={[
        "Context: what forced a choice — a constraint, a failure, a cost.",
        "Decision: what is decided, in one place the code can cite.",
        "Consequences: what it costs, and what it rules out.",
        `Status: proposed (${n("proposed")}), accepted (${n("accepted")}), superseded by a later record (${n("superseded")}).`,
      ]}
    />
  );
}

// ───────────────────────── Field notes ─────────────────────────

/** The shape every case file has (docs/LESSONS.md: symptom → cause → fix · guard). */
export function CaseAnatomy() {
  return (
    <Draw
      w={1200}
      h={300}
      boxes={[
        { x: 0, y: 60, w: 230, h: 110, title: "Symptom", lines: ["what a live run showed", "in bold, first"] },
        { x: 320, y: 60, w: 230, h: 110, title: "Cause", lines: ["why it happened —", "often not the model"] },
        { x: 640, y: 60, w: 230, h: 110, title: "Fix", lines: ["after the arrow"] },
        { x: 960, y: 60, w: 240, h: 110, title: "Guard", lines: ["a test or a check", "or a lesson, written down"], tone: "ink" },
      ]}
      edges={[{ d: "M230 115 H 320" }, { d: "M550 115 H 640" }, { d: "M870 115 H 960" }, { d: "M1080 170 V 240 H 115 V 170", dashed: true }]}
      labels={[{ x: 600, y: 240, text: "so the same bug can't come back silently" }]}
      steps={[
        "Symptom: what a live run showed.",
        "Cause: why it happened — often the harness or the measurement, not the model.",
        "Fix: what changed.",
        "Guard: a test or a check, so the same bug can't come back silently — or the lesson, written down.",
      ]}
    />
  );
}

/** Where in the measurement chain each "numbers lied" case broke. */
export function WhereNumbersBroke({ marks }: { marks: Record<string, ReactNode[]> }) {
  const stages = [
    ["thesis", "Thesis", "what is being tested"],
    ["run", "Run", "the agent on a bug"],
    ["score", "Score", "against the answer key"],
    ["report", "Report", "evals/reports/<date>"],
    ["site", "Site · README", "what people read"],
  ];
  const w = 200;
  const gap = 50;
  return (
    <Draw
      w={1200}
      h={190}
      boxes={stages.map(([id, t, l], i) => ({
        x: i * (w + gap),
        y: 20,
        w,
        h: 150,
        title: t,
        lines: [l, ...(marks[id] ?? [])],
        tone: (marks[id]?.length ? "plain" : "sunk") as "plain" | "sunk",
      }))}
      edges={stages.slice(1).map((_, i) => ({ d: `M${i * (w + gap) + w} 95 H ${(i + 1) * (w + gap)}` }))}
      steps={stages.map(([id, t, l]) => (
        <>
          <b className="font-medium text-t1">{t}</b> — {l}
          {marks[id]?.length ? <> · {marks[id]}</> : null}
        </>
      ))}
    />
  );
}

/** The two escapes the 2026-10-16 audit reproduced, and what closed each (ADR 0009). */
export function Escapes() {
  return (
    <Draw
      w={1200}
      h={330}
      svg={<line x1={255} x2={255} y1={0} y2={330} stroke="var(--fg)" strokeDasharray="6 5" />}
      boxes={[
        { x: 0, y: 40, w: 220, h: 100, title: "A planted .git", tag: "container", lines: ["config sets", "core.fsmonitor"] },
        { x: 290, y: 40, w: 200, h: 100, title: "host git diff", lines: ["discovers that .git"] },
        { x: 560, y: 40, w: 240, h: 100, title: "runs a command", tag: "before", lines: ["on the host"], tone: "hatch" },
        { x: 870, y: 40, w: 330, h: 100, title: "core.hostgit", tag: "now", lines: ["a verified worktree admin dir", "hooks and fsmonitor off"], tone: "ink" },
        { x: 0, y: 200, w: 220, h: 100, title: "A symlink", tag: "container", lines: ["to a .env outside", "the worktree"] },
        { x: 290, y: 200, w: 200, h: 100, title: "host-side grep", lines: ["follows it"] },
        { x: 560, y: 200, w: 240, h: 100, title: "returns the secret", tag: "before", lines: ["to the agent"], tone: "hatch" },
        { x: 870, y: 200, w: 330, h: 100, title: "walk_files", tag: "now", lines: ["host-side walks never", "follow symlinks"], tone: "ink" },
      ]}
      edges={[
        { d: "M220 90 H 290" },
        { d: "M490 90 H 560" },
        { d: "M800 90 H 870", dashed: true },
        { d: "M220 250 H 290" },
        { d: "M490 250 H 560" },
        { d: "M800 250 H 870", dashed: true },
      ]}
      labels={[
        { x: 245, y: 14, text: "container", anchor: "r", boxed: false },
        { x: 265, y: 14, text: "host", anchor: "l", boxed: false },
      ]}
      steps={[
        "A .git planted by the container, with core.fsmonitor set, made the host's git diff run a command. Now host git uses a verified worktree admin dir with hooks and fsmonitor off (core.hostgit).",
        "A symlink to a .env outside the worktree was returned by the host-side grep tool. Now host-side walks never follow symlinks (walk_files).",
      ]}
    />
  );
}

// ───────────────────────── Lessons ─────────────────────────

/** How each section's entries close: with a guard, a lesson, both, or neither. */
export function HowEntriesClose({ entries }: { entries: Lesson[] }) {
  const sections = [...new Set(entries.map((e) => e.section))];
  const kind = (e: Lesson) => {
    if (!e.fix) return "open";
    const g = e.guards.some((x) => x.startsWith("Guard"));
    const l = e.guards.some((x) => x.startsWith("Lesson"));
    return g && l ? "both" : g ? "guard" : l ? "lesson" : "fix";
  };
  const KINDS: [string, string, string][] = [
    ["guard", "fix + a guard (test or check)", "bg-t1"],
    ["both", "fix + guard + lesson", "bg-t2"],
    ["lesson", "fix + a lesson", "hatch-ink"],
    ["fix", "fix only", "bg-surface"],
    ["open", "no fix yet", "bg-sunk"],
  ];
  return (
    <div>
      <div className="grid gap-3">
        {sections.map((s) => {
          const es = entries.filter((e) => e.section === s);
          return (
            <div key={s} className="grid items-center gap-x-4 gap-y-1 sm:grid-cols-[minmax(0,260px)_minmax(0,1fr)_40px]">
              <span className="text-[13.5px] text-t2">{s.replace(/^\d+\.\s*/, "")}</span>
              <span className="flex h-4 border border-line-strong">
                {KINDS.map(([k, , cls]) => {
                  const n = es.filter((e) => kind(e) === k).length;
                  return n ? <span key={k} className={`${cls} border-r border-line-strong last:border-r-0`} style={{ width: `${(n / es.length) * 100}%` }} title={`${n}`} /> : null;
                })}
              </span>
              <span className="font-mono text-[12px] text-t1 sm:text-right">{es.length}</span>
            </div>
          );
        })}
      </div>
      <div className="mt-5 flex flex-wrap gap-x-6 gap-y-2 font-mono text-[11px] text-t3">
        {KINDS.map(([k, l, cls]) => (
          <span key={k} className="inline-flex items-center gap-2">
            <i className={`inline-block h-3 w-4 border border-line-strong ${cls}`} />
            {l}
          </span>
        ))}
      </div>
    </div>
  );
}

// ───────────────────────── Lab notebook ─────────────────────────

/** How one number on this site is made, and where the answer key sits (docs/ARCHITECTURE.md, PLAN §5). */
export function HowANumberIsMade() {
  return (
    <Draw
      w={1200}
      h={360}
      svg={<line x1={20} x2={1180} y1={225} y2={225} stroke="var(--fg)" strokeDasharray="6 5" />}
      boxes={[
        { x: 0, y: 40, w: 180, h: 110, title: "Inject", lines: ["a release commit", "in MiniRide"] },
        { x: 230, y: 40, w: 180, h: 110, title: "Trigger", lines: ["rider fleet", "flags · toxics"] },
        { x: 460, y: 40, w: 180, h: 110, title: "Discover", lines: ["Vitals issue", "or BugDrop report"] },
        { x: 690, y: 40, w: 200, h: 110, title: "Agent run", lines: ["never sees", "the answer key"], tone: "ink" },
        { x: 940, y: 40, w: 260, h: 110, title: "results.csv → report", lines: ["evals/reports/<date>", "→ this site, at build"] },
        { x: 690, y: 255, w: 200, h: 90, title: "Scorer", lines: ["root cause vs key", "hidden tests on the fix"] },
        { x: 230, y: 255, w: 360, h: 90, title: "groundtruth/", lines: ["answer key · reference fix · hidden tests", "never mounted into a sandbox"], tone: "hatch" },
      ]}
      edges={[
        { d: "M180 95 H 230" },
        { d: "M410 95 H 460" },
        { d: "M640 95 H 690" },
        { d: "M790 150 V 255" },
        { d: "M590 300 H 690" },
        { d: "M890 300 H 1070 V 150" },
      ]}
      labels={[
        { x: 1180, y: 210, text: "the agent's side ↑ · the evaluator's side ↓", anchor: "r", boxed: false },
      ]}
      steps={[
        "A catalog bug is injected into MiniRide as an ordinary release commit.",
        "Simulated riders trigger it; flags, toxics and incidents are applied.",
        "Vitals or BugDrop discovers it, the way a real bug would be found.",
        "The agent runs on that issue and never sees the answer key.",
        "The scorer compares its root cause with the answer key and runs hidden tests on its fix — both from groundtruth/, which is never mounted into a sandbox.",
        "Scores land in results.csv and the report; this site reads them at build time.",
      ]}
    />
  );
}

/** Finding the culprit commit with the agent's own test (docs/LESSONS.md › bisect entries). An illustration. */
export function BisectProof() {
  const tags = 9;
  const X = (i: number) => 1140 - i * 125; // newest at the right
  const probes = [0, 1, 2, 4, 8];
  const good = 4;
  return (
    <Draw
      w={1200}
      h={300}
      svg={
        <>
          <line x1={40} x2={1170} y1={130} y2={130} stroke="var(--fg)" strokeWidth={1.5} />
          {Array.from({ length: tags }, (_, i) => {
            const probed = probes.includes(i) && i <= good;
            const pass = i >= good;
            return (
              <g key={i}>
                <rect x={X(i) - 8} y={122} width={16} height={16} fill={probed ? (pass ? "var(--raised)" : "var(--fg)") : "var(--raised)"} stroke={probed ? "var(--fg)" : "var(--line-2)"} />
                <text x={X(i)} y={160} textAnchor="middle" fontSize="11" fontFamily="var(--font-mono)" fill={probed ? "var(--fg)" : "var(--fg-4)"}>
                  {i === 0 ? "newest" : `−${i}`}
                </text>
              </g>
            );
          })}
          <path d={`M${X(good)} 190 V 215 H ${X(2)} V 190`} fill="none" stroke="var(--fg)" />
        </>
      }
      boxes={[]}
      labels={[
        { x: X(0), y: 90, text: "fails", boxed: true },
        { x: X(1), y: 90, text: "fails" },
        { x: X(2), y: 90, text: "fails" },
        { x: X(4), y: 90, text: "passes — a good release" },
        { x: (X(good) + X(2)) / 2, y: 240, text: "git bisect between them → the first failing commit" },
        { x: 40, y: 30, text: "probe tags at doubling distances: 1st, 2nd, 4th, 8th … oldest", anchor: "l", boxed: false },
      ]}
      steps={[
        "Take the agent's validated reproduction test.",
        "Run it on release tags at doubling distances back from the newest — 1st, 2nd, 4th, 8th … oldest — until one passes.",
        "That passing release is good; the next newer one probed fails.",
        "git bisect between them finds the first commit where the test fails — a result anyone can re-run.",
      ]}
    />
  );
}
