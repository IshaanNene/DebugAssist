import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { ChapterPage, Figure, Section } from "@/components/Page";
import { FingerprintFlow } from "@/components/figs";
import { discoveryTimes, results } from "@/lib/data";
import { templates } from "@/lib/docs";
import { inline, parse, type Block } from "@/lib/md";
import { docSection } from "@/lib/docs";

export const metadata: Metadata = {
  title: "Discovery — DebugAssist",
  description: "How a bug reaches DebugAssist: crash analytics, in-app bug reports, GitHub issues and failing CI checks, deduplicated and triaged before any agent runs.",
};

const TOC = [
  { id: "paths", text: "Five ways in" },
  { id: "vitals", text: "Vitals: crashes" },
  { id: "bugdrop", text: "BugDrop: reports" },
  { id: "github", text: "GitHub: issues and CI" },
  { id: "gate", text: "Before an agent runs" },
  { id: "latency", text: "Discovery to answer" },
  { id: "catalog", text: "How each bug surfaces" },
];

// The reference forms N0 ingest accepts (packages/pipeline/src/debugassist/pipeline/nodes/intake.py).
const REFS: [string, string, string][] = [
  ["VIT-1001", "Vitals issue", "a new crash group, or a regression reopened on a newer version"],
  ["BD-1001", "BugDrop report", "a rider's report with screenshot, logs and UI timeline"],
  ["GH-…", "frozen GitHub issue", "a recorded issue, replayed for evaluation"],
  ["GHA:owner/repo#123", "GitHub App issue", "an issue labeled debugassist on an installed repository"],
  ["GHCI:owner/repo@id", "failed CI check", "a check that failed on an installed repository's default branch"],
];

const W = 1200;
const H = 440;
type Box = { x: number; y: number; w: number; h: number };
const pc = (b: Box) => ({ left: `${(b.x / W) * 100}%`, top: `${(b.y / H) * 100}%`, width: `${(b.w / W) * 100}%`, height: `${(b.h / H) * 100}%` });

const RIDER: Box = { x: 0, y: 150, w: 210, h: 140 };
const VIT: Box = { x: 300, y: 20, w: 250, h: 110 };
const BD: Box = { x: 300, y: 165, w: 250, h: 110 };
const GH: Box = { x: 300, y: 310, w: 250, h: 110 };
const INGEST: Box = { x: 640, y: 165, w: 170, h: 110 };
const GATE: Box = { x: 870, y: 165, w: 180, h: 110 };
const RUN: Box = { x: 1100, y: 185, w: 100, h: 70 };
const mid = (b: Box) => b.y + b.h / 2;

function Node({ b, title, tag, children, ink }: { b: Box; title: string; tag?: string; children?: ReactNode; ink?: boolean }) {
  return (
    <div className={`absolute flex flex-col justify-between border p-3 ${ink ? "border-t1 bg-t1 text-surface" : "border-line-strong bg-surface"}`} style={pc(b)}>
      <div className="flex items-baseline justify-between gap-2">
        <span className={`text-[14.5px] font-medium tracking-[-0.01em] ${ink ? "text-surface" : "text-t1"}`}>{title}</span>
        {tag && <span className={`font-mono text-[10.5px] ${ink ? "text-surface/70" : "text-t3"}`}>{tag}</span>}
      </div>
      {children && <div className={`font-mono text-[10.5px] leading-[1.5] ${ink ? "text-surface/80" : "text-t3"}`}>{children}</div>}
    </div>
  );
}

function Flow({ dedup, triage }: { dedup: string; triage: string }) {
  const edges = [
    `M${RIDER.x + RIDER.w} ${mid(RIDER) - 20} H 255 V ${mid(VIT)} H ${VIT.x}`,
    `M${RIDER.x + RIDER.w} ${mid(BD)} H ${BD.x}`,
    `M${VIT.x + VIT.w} ${mid(VIT)} H 595 V ${mid(INGEST) - 30} H ${INGEST.x}`,
    `M${BD.x + BD.w} ${mid(BD)} H ${INGEST.x}`,
    `M${GH.x + GH.w} ${mid(GH)} H 595 V ${mid(INGEST) + 30} H ${INGEST.x}`,
    `M${INGEST.x + INGEST.w} ${mid(INGEST)} H ${GATE.x}`,
    `M${GATE.x + GATE.w} ${mid(GATE)} H ${RUN.x}`,
  ];
  return (
    <>
      <div className="relative hidden aspect-[1200/440] w-full lg:block">
        <svg viewBox={`0 0 ${W} ${H}`} className="absolute inset-0 h-full w-full overflow-visible" aria-hidden>
          <defs>
            <marker id="da" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="8" markerHeight="8" orient="auto">
              <path d="M0 0 L8 4 L0 8 z" fill="var(--line-strong)" />
            </marker>
          </defs>
          {edges.map((d) => (
            <path key={d} d={d} fill="none" stroke="var(--line-strong)" strokeWidth={1} markerEnd="url(#da)" />
          ))}
        </svg>
        <Node b={RIDER} title="Rider session" tag="SDKs">
          crashes · hangs · jank
          <br />
          breadcrumbs · flags
          <br />
          &ldquo;Report a bug&rdquo; sheet
        </Node>
        <Node b={VIT} title="Vitals" tag="VIT-…">
          group by stack fingerprint
          <br />
          reopen as regression
        </Node>
        <Node b={BD} title="BugDrop" tag="BD-…">
          screenshot · logs · UI timeline
          <br />
          redacted twice
        </Node>
        <Node b={GH} title="GitHub" tag="GHA: · GHCI:">
          label debugassist
          <br />
          or a failed check on main
        </Node>
        <Node b={INGEST} title="Ingest" tag="N0 · code">
          one Issue, whatever
          <br />
          the source
        </Node>
        <Node b={GATE} title="Triage" tag={`${dedup} · ${triage}`}>
          duplicate?
          <br />
          worth an agent run?
        </Node>
        <Node b={RUN} title="Run" ink />
        <span className="absolute border border-line-2 bg-surface px-2 py-0.5 font-mono text-[10.5px] text-t3" style={{ left: `${(305 / W) * 100}%`, top: `${(293 / H) * 100}%`, transform: "translateY(-50%)" }}>
          a maintainer, not the rider
        </span>
      </div>
      <ol className="grid gap-2 lg:hidden">
        {["Rider session — SDKs capture crashes, hangs, breadcrumbs and bug reports", "Vitals (VIT-…), BugDrop (BD-…) or GitHub (GHA:, GHCI:)", "Ingest — one Issue, whatever the source", `Triage — ${dedup} duplicate? ${triage} worth a run?`, "Run"].map((t, i) => (
          <li key={t} className="flex gap-3 border border-line bg-surface p-3 text-[14px] text-t2">
            <span className="font-mono text-[11px] text-t4">{String(i + 1).padStart(2, "0")}</span>
            {t}
          </li>
        ))}
      </ol>
    </>
  );
}

const fmt = (s: number) => (s < 60 ? `${s.toFixed(0)} s` : `${Math.floor(s / 60)} min ${String(Math.round(s % 60)).padStart(2, "0")} s`);

function Spec({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="border-t border-line">
      {rows.map(([k, v]) => (
        <div key={k} className="fx grid gap-1 border-b border-line py-4 md:grid-cols-[220px_minmax(0,1fr)] md:gap-8">
          <dt className="font-mono text-[12px] text-t1">{k}</dt>
          <dd className="max-w-[68ch] text-[15px] leading-[1.6] text-t2">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export default function DiscoveryPage() {
  const data = results();
  const times = discoveryTimes(data);
  const tpl = templates();
  const d01 = tpl.find((t) => t.id === "D01");
  const d02 = tpl.find((t) => t.id === "D02");
  const arch = "docs/ARCHITECTURE.md";
  const catalog = parse(docSection(arch, "Bug catalog and scenarios (P2b)")).find((b): b is Extract<Block, { t: "table" }> => b.t === "table");

  return (
    <ChapterPage
      chapter="/discovery/"
      title={
        <>
          Nobody files the ticket. <span className="hl">The crash does.</span>
        </>
      }
      lead={
        <>
          A bug reaches DebugAssist the way it reaches an on-call engineer: a crash spike in analytics, a rider shaking the
          phone to report it, an issue on GitHub, a red check on main. Every path becomes the same Issue, then is
          deduplicated and triaged by Clef before any agent spends a token on it.
        </>
      }
      sources={[arch, "packages/pipeline/src/debugassist/pipeline/nodes/intake.py", "docs/github-app.md", `evals/reports/${data.report}/results.csv`]}
      toc={TOC}
    >
      <Section id="paths" title="Five ways in" aside="N0 ingest">
        <Figure n="1" title="from a rider's session to a run" note="every path becomes one Issue">
          <Flow dedup="D02" triage="D01" />
        </Figure>
        <div className="fx mt-8 overflow-x-auto border border-line bg-surface">
          <table className="w-full min-w-[640px] border-collapse text-left">
            <thead>
              <tr className="border-b border-line bg-sunk/60 font-mono text-[10.5px] uppercase tracking-[0.08em] text-t3">
                <th className="px-5 py-3 font-normal">Reference</th>
                <th className="px-5 py-3 font-normal">Source</th>
                <th className="px-5 py-3 font-normal">What it is</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {REFS.map(([r, s, w]) => (
                <tr key={r}>
                  <td className="px-5 py-3 font-mono text-[12.5px] text-t1">{r}</td>
                  <td className="px-5 py-3 text-[14px] text-t1">{s}</td>
                  <td className="px-5 py-3 text-[14px] text-t3">{w}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section id="vitals" title="Vitals: crashes" aside="≈ crash and performance analytics">
        <Spec
          rows={[
            ["Browser SDK", "Crashes (error, unhandledrejection), hangs from a 1 s heartbeat, jank from long tasks, background CPU from timer wake-ups, breadcrumbs with analytics events and HTTP calls, console logs, flag exposures, device and city."],
            ["Server SDKs", "Python (an ASGI hook), Go (panic-recovering middleware) and Node (uncaught errors and unexpected resolver errors)."],
            ["Grouping", "Events group by a normalized stack fingerprint: in-app frames only, without line numbers or asset hashes, so one bug is one group across builds."],
            ["Regressions", "A new group opens an issue; a group seen again on a newer version reopens its issue as a regression."],
            ["Denominators", "Sessions carry flag exposures, so a crash rate can be split by version, OS, browser, device, city, locale or flag — and a flag's exposure compared between all sessions and affected ones."],
            ["Symbolication", "Source maps, with the enclosing function recovered, so the root-cause step reads real names."],
          ]}
        />
        <Figure n="2" title="from a stack trace to an issue" note="one bug, one group, across builds" className="mt-10">
          <FingerprintFlow />
        </Figure>
      </Section>

      <Section id="bugdrop" title="BugDrop: reports" aside="≈ in-app bug reporting">
        <Spec
          rows={[
            ["The report", "A description and up to four images, from a “Report a bug” sheet inside the app."],
            ["Screenshot", "Of the app's own DOM only — the reporter's UI is filtered out; it falls back to the page when the app root is blank, which is itself evidence."],
            ["Ring buffers", "Network (method, URL template, status, timing — never bodies), GraphQL operations with error codes, console, analytics, UI-state snapshots and performance samples."],
            ["Redaction", "On the device before upload, and again on the server with the same redactor the pipeline uses."],
            ["Derived evidence", "A UI-state timeline: visibility intervals and the longest hidden period — how a battery bug that only runs in the background gets caught."],
          ]}
        />
      </Section>

      <Section id="github" title="GitHub: issues and CI" aside={<Link href="/repo/" className="underline decoration-line-2 underline-offset-[3px] hover:text-t1">the GitHub App →</Link>}>
        <Spec
          rows={[
            ["A labeled issue", <>On a repository the App is installed on, the label <code className="font-mono text-[13px] text-t1">debugassist</code> is the consent to run. The App checks out the default branch and investigates it there.</>],
            ["A failed check", <>With <code className="font-mono text-[13px] text-t1">check_run</code> subscribed, a check that fails or times out on the default branch is queued once. Its title, summary and text are the report; checks on other branches, the App&apos;s own included, are ignored.</>],
            ["Delivery", "A poll does the work; the optional webhook only queues, after checking the HMAC signature and dropping repeated deliveries."],
          ]}
        />
      </Section>

      <Section id="gate" title="Before an agent runs" aside="two Clef decisions">
        <div className="grid gap-px border border-line bg-line md:grid-cols-2">
          {[d02, d01].map(
            (t) =>
              t && (
                <Link key={t.id} href={`/decisions/#${t.id}`} className="fx group bg-surface p-6 transition-colors hover:bg-sunk/40">
                  <div className="flex items-baseline justify-between">
                    <span className="font-mono text-[12px] text-t1">
                      {t.id} · {t.name}
                    </span>
                    <span className="font-mono text-[11px] text-t3">
                      τ {t.tauLow} / {t.tauHigh}
                    </span>
                  </div>
                  <p className="mt-3 text-[15px] leading-[1.6] text-t2">{t.description}</p>
                  <p className="mt-4 font-mono text-[11.5px] text-t3">
                    act → {typeof t.act === "string" ? t.act : t.act.map(([, v]) => v).filter((v, i, a) => a.indexOf(v) === i).join(" / ")} · unsure → {t.escalate} · default →{" "}
                    {t.safeDefault}
                  </p>
                </Link>
              ),
          )}
        </div>
        <p className="fx mt-6 max-w-[68ch] text-[14.5px] leading-[1.6] text-t3">
          A report that matches an open issue is attached to it rather than run again; in the evaluation, when D02 attaches
          a BugDrop report to the same bug&apos;s Vitals issue, the run investigates that issue instead.
        </p>
      </Section>

      {times && (
        <Section id="latency" title="Discovery to answer" aside={`${times.runs} runs · evals/reports/${times.report}`}>
          <div className="grid gap-px border border-line bg-line sm:grid-cols-2">
            {[
              ["Discovery → root cause", times.rca],
              ["Discovery → run finished", times.end],
            ].map(([k, v]) => {
              const s = v as { median: number; min: number; max: number };
              return (
                <div key={k as string} className="fx bg-surface p-6">
                  <div className="label text-[10.5px] text-t4">{k as string} · median</div>
                  <div className="mt-2 font-mono text-[40px] font-medium leading-none tracking-[-0.03em] text-t1">{fmt(s.median)}</div>
                  <div className="mt-3 font-mono text-[12px] text-t3">
                    range {fmt(s.min)} – {fmt(s.max)}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="fx mt-3 overflow-x-auto border border-line bg-surface">
            <table className="w-full min-w-[520px] border-collapse text-left">
              <thead>
                <tr className="border-b border-line bg-sunk/60 font-mono text-[10.5px] uppercase tracking-[0.08em] text-t3">
                  <th className="px-5 py-3 font-normal">Source</th>
                  <th className="px-5 py-3 text-right font-normal">Runs</th>
                  <th className="px-5 py-3 text-right font-normal">→ root cause</th>
                  <th className="px-5 py-3 text-right font-normal">→ finished</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line font-mono text-[13px]">
                {times.sources.map((s) => (
                  <tr key={s.prefix}>
                    <td className="px-5 py-3 text-t1">
                      {s.source} <span className="text-t4">{s.prefix}-…</span>
                    </td>
                    <td className="px-5 py-3 text-right text-t2">{s.runs}</td>
                    <td className="px-5 py-3 text-right text-t1">{fmt(s.rcaMedian)}</td>
                    <td className="px-5 py-3 text-right text-t1">{fmt(s.endMedian)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="fx mt-6 max-w-[70ch] text-[14.5px] leading-[1.6] text-t3">
            Measured from the moment the source created the issue, in the full-catalog evaluation run. A row whose source
            clock was ahead of the run (a negative duration) is dropped, not clamped to zero. Medians, so one slow run
            cannot move them.
          </p>
        </Section>
      )}

      {catalog && (
        <Section id="catalog" title="How each bug surfaces" aside={`${catalog.rows.length} of ${data.catalog.total} catalog bugs, as ${arch} lists them`}>
          <div className="fx overflow-x-auto border border-line bg-surface">
            <table className="w-full min-w-[820px] border-collapse text-left">
              <thead>
                <tr className="border-b border-line bg-sunk/60 font-mono text-[10.5px] uppercase tracking-[0.08em] text-t3">
                  {catalog.head.map((h, i) => (
                    <th key={i} className="px-5 py-3 font-normal">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {catalog.rows.map((r, i) => (
                  <tr key={i} className="align-top">
                    {r.map((c, j) => (
                      <td key={j} className={`px-5 py-3 text-[13.5px] leading-[1.5] ${j === 0 ? "font-medium text-t1" : j === r.length - 1 ? "text-t1" : "text-t3"}`}>
                        {inline(c, arch)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="fx mt-6 max-w-[70ch] text-[14.5px] leading-[1.6] text-t3">
            Each bug is shipped as an ordinary release commit, then found only through these sources, the way a real one
            would be. How the catalog is built and triggered is on the{" "}
            <Link className="text-t1 underline decoration-line-2 underline-offset-[3px] hover:decoration-t1" href="/testbed/">
              test bed
            </Link>{" "}
            page.
          </p>
        </Section>
      )}
    </ChapterPage>
  );
}
