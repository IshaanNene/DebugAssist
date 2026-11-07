import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { ChapterPage, Figure, Section } from "@/components/Page";
import { results } from "@/lib/data";
import { docSection } from "@/lib/docs";
import { Markdown, inline, parse, type Block } from "@/lib/md";

export const metadata: Metadata = {
  title: "Test bed — DebugAssist",
  description: "MiniRide, the ride-hailing system DebugAssist is evaluated on: its services, its stand-ins for production tooling, and how each catalog bug is shipped, triggered and verified.",
};

const ARCH = "docs/ARCHITECTURE.md";

const TOC = [
  { id: "miniride", text: "MiniRide" },
  { id: "standins", text: "Stand-ins for production" },
  { id: "inject", text: "Shipping a bug" },
  { id: "verify", text: "Proving the catalog" },
];

const W = 1200;
const H = 400;
type Box = { x: number; y: number; w: number; h: number };
const pc = (b: Box) => ({ left: `${(b.x / W) * 100}%`, top: `${(b.y / H) * 100}%`, width: `${(b.w / W) * 100}%`, height: `${(b.h / H) * 100}%` });

function Part({ b, title, sub, children, hatch }: { b: Box; title: string; sub: string; children?: ReactNode; hatch?: boolean }) {
  return (
    <div className={`absolute flex flex-col justify-between border border-line-strong p-3 ${hatch ? "hatch bg-sunk" : "bg-surface"}`} style={pc(b)}>
      <div>
        <div className="text-[14.5px] font-medium tracking-[-0.01em] text-t1">{title}</div>
        <div className="font-mono text-[10.5px] text-t3">{sub}</div>
      </div>
      {children && <div className="font-mono text-[10.5px] leading-[1.5] text-t3">{children}</div>}
    </div>
  );
}

// The system as docs/ARCHITECTURE.md describes it: client → gateway (GraphQL) → dispatch and payments; flags from
// Unleash; every component ships OpenTelemetry to the collector, which feeds Jaeger, Loki and Prometheus.
const CLIENT: Box = { x: 0, y: 40, w: 230, h: 130 };
const GATEWAY: Box = { x: 320, y: 40, w: 230, h: 130 };
const DISPATCH: Box = { x: 650, y: 0, w: 230, h: 95 };
const PAYMENTS: Box = { x: 650, y: 115, w: 230, h: 95 };
const PG: Box = { x: 970, y: 0, w: 230, h: 95 };
const FLAGS: Box = { x: 970, y: 115, w: 230, h: 95 };
const OTEL: Box = { x: 0, y: 290, w: 1200, h: 90 };

function MiniRideMap() {
  const e = [
    `M${CLIENT.x + CLIENT.w} 105 H ${GATEWAY.x}`,
    `M${GATEWAY.x + GATEWAY.w} 90 H 600 V 47 H ${DISPATCH.x}`,
    `M${GATEWAY.x + GATEWAY.w} 120 H 600 V 162 H ${PAYMENTS.x}`,
    `M${DISPATCH.x + DISPATCH.w} 47 H ${PG.x}`,
    `M${PAYMENTS.x + PAYMENTS.w} 162 H ${FLAGS.x}`,
  ];
  const otel = [115, 435, 765].map((x) => `M${x} ${x === 765 ? 210 : 170} V ${OTEL.y}`);
  return (
    <div className="relative hidden aspect-[1200/400] w-full lg:block">
      <svg viewBox={`0 0 ${W} ${H}`} className="absolute inset-0 h-full w-full overflow-visible" aria-hidden>
        <defs>
          <marker id="ta" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="8" markerHeight="8" orient="auto">
            <path d="M0 0 L8 4 L0 8 z" fill="var(--line-strong)" />
          </marker>
        </defs>
        {e.map((d) => (
          <path key={d} d={d} fill="none" stroke="var(--line-strong)" strokeWidth={1} markerEnd="url(#ta)" />
        ))}
        {otel.map((d) => (
          <path key={d} d={d} fill="none" stroke="var(--line-strong)" strokeWidth={1} strokeDasharray="4 4" markerEnd="url(#ta)" />
        ))}
      </svg>
      <Part b={CLIENT} title="client" sub="TypeScript · React 19 · Vite">
        booking · notification center
        <br />
        push deep links · ETA poller
      </Part>
      <Part b={GATEWAY} title="gateway" sub="Node 22 · GraphQL Yoga">
        rider API · notification store
        <br />
        logs every operation
      </Part>
      <Part b={DISPATCH} title="dispatch" sub="Python 3.13 · FastAPI" />
      <Part b={PAYMENTS} title="payments" sub="Go · per-city tariffs" />
      <Part b={PG} title="Postgres" sub="behind Toxiproxy" hatch />
      <Part b={FLAGS} title="Unleash" sub="notif_router_v2 · surge_pricing" hatch />
      <span className="absolute border border-line-2 bg-surface px-2 py-0.5 font-mono text-[10.5px] text-t3" style={{ left: `${(565 / W) * 100}%`, top: `${(90 / H) * 100}%`, transform: "translate(-50%,-50%)" }}>
        GraphQL
      </span>
      <div className="absolute flex items-center justify-between border border-t1 bg-t1 px-4 text-surface" style={pc(OTEL)}>
        <div>
          <div className="text-[14.5px] font-medium">OpenTelemetry collector</div>
          <div className="font-mono text-[10.5px] text-surface/70">W3C trace context browser → gateway → dispatch / payments · x-session-id · x-app-version</div>
        </div>
        <div className="hidden gap-2 font-mono text-[11px] xl:flex">
          {["Jaeger", "Loki", "Prometheus"].map((t) => (
            <span key={t} className="border border-surface/30 px-2 py-0.5">
              {t}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

// Injection, step by step, as docs/ARCHITECTURE.md lists it.
const STEPS: [string, string][] = [
  ["Branch", "A release/<version> branch is cut from the base tag in the target repository."],
  ["Commit", "The regression is applied with git am, authored and committed by a fictional MiniRide engineer — an ordinary-looking change."],
  ["Release", "The repository's own scripts/release.sh tags it, and the affected services are rebuilt."],
  ["Adoption", "The previous client release keeps serving a share of sessions on :8081, the way a gradual rollout does."],
  ["Conditions", "Then whatever the bug needs: an Unleash rollout, Toxiproxy toxics on the database link, a declared incident."],
  ["Traffic", "A Playwright rider fleet — devices, locales, throttled and lossy networks, background time, push launches and bug reports — plus Locust load."],
];

const table = (md: string) => parse(md).find((b): b is Extract<Block, { t: "table" }> => b.t === "table");

function Table({ t, from, wide = 760 }: { t: Extract<Block, { t: "table" }>; from: string; wide?: number }) {
  return (
    <div className="fx overflow-x-auto border border-line bg-surface">
      <table className="w-full border-collapse text-left" style={{ minWidth: wide }}>
        <thead>
          <tr className="border-b border-line bg-sunk/60 font-mono text-[10.5px] uppercase tracking-[0.08em] text-t3">
            {t.head.map((h, i) => (
              <th key={i} className="px-5 py-3 font-normal">
                {inline(h, from)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {t.rows.map((r, i) => (
            <tr key={i} className="align-top">
              {r.map((c, j) => (
                <td key={j} className={`px-5 py-3 text-[13.5px] leading-[1.5] ${j === 0 ? "text-t1" : "text-t2"}`}>
                  {inline(c, from)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function TestbedPage() {
  const data = results();
  const miniride = docSection(ARCH, "Target system: MiniRide");
  const components = table(miniride);
  const contract = miniride
    .split("\n\n")
    .filter((p) => /^(Telemetry contract|Feature flags)/.test(p.trim()))
    .join("\n\n");
  const standins = table(docSection(ARCH, "Stand-ins for internal infrastructure"));
  const tree = docSection(ARCH, "Bug catalog and scenarios (P2b)").match(/```\n([\s\S]*?)```/)?.[1] ?? "";

  return (
    <ChapterPage
      chapter="/testbed/"
      title={
        <>
          A small production, <span className="hl">built to break.</span>
        </>
      }
      lead={
        <>
          An agent that debugs production needs a production to debug. MiniRide is a four-service ride-hailing app with real
          telemetry, feature flags and on-call owners; each of the {data.catalog.total} catalog bugs ships into it as an
          ordinary release, and is found only the way a real one would be.
        </>
      }
      sources={[ARCH, "packages/scenarios", "packages/simulator"]}
      toc={TOC}
    >
      <Section id="miniride" title="MiniRide" aside="IshaanNene/miniride-client · miniride-services">
        <Figure n="1" title="the system under test" note="every component ships telemetry">
          <MiniRideMap />
          <div className="lg:hidden">{components && <Table t={components} from={ARCH} />}</div>
        </Figure>
        <div className="mt-8 hidden lg:block">{components && <Table t={components} from={ARCH} wide={900} />}</div>
        <div className="fx mt-8 max-w-[80ch]">
          <Markdown src={contract} from={ARCH} />
        </div>
      </Section>

      <Section id="standins" title="Stand-ins for production" aside="what each internal tool becomes here">
        {standins && <Table t={standins} from={ARCH} wide={720} />}
      </Section>

      <Section id="inject" title="Shipping a bug" aside="debugassist scenario inject · trigger">
        <ol className="grid gap-px border border-line bg-line md:grid-cols-2 lg:grid-cols-3">
          {STEPS.map(([t, b], i) => (
            <li key={t} className="fx bg-surface p-6" style={{ ["--i" as string]: i * 0.4 }}>
              <div className="flex items-baseline gap-3">
                <span className="font-mono text-[12px] text-t4">{String(i + 1).padStart(2, "0")}</span>
                <span className="text-[17px] font-medium tracking-[-0.015em] text-t1">{t}</span>
              </div>
              <p className="mt-3 text-[14.5px] leading-[1.6] text-t2">{b}</p>
            </li>
          ))}
        </ol>
        <p className="fx mt-6 max-w-[70ch] text-[14.5px] leading-[1.6] text-t3">
          The answer key lives outside the target repositories and is never mounted into a sandbox; regression commits name
          no catalog ID. How each bug then surfaces — crash group, rider report or both — is on the{" "}
          <Link className="text-t1 underline decoration-line-2 underline-offset-[3px] hover:decoration-t1" href="/discovery/#catalog">
            discovery
          </Link>{" "}
          page.
        </p>
      </Section>

      <Section id="verify" title="Proving the catalog" aside="debugassist scenario verify">
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="fx">
            <Spec
              rows={[
                ["applies", "In a throwaway worktree, each regression applies cleanly to its base release."],
                ["fails", "Its hidden test fails on the regressed release — so the bug is real, and reachable by a test."],
                ["fixes", "The reference fix makes every test pass, hidden ones included."],
                ["resets", "reset restores main, baseline flags and a clean environment between bugs."],
              ]}
            />
          </div>
          <pre className="fx overflow-x-auto border border-line bg-sunk p-5 font-mono text-[12px] leading-[1.7] text-t2">{tree}</pre>
        </div>
      </Section>
    </ChapterPage>
  );
}

function Spec({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="border-t border-line">
      {rows.map(([k, v]) => (
        <div key={k} className="grid gap-1 border-b border-line py-4 sm:grid-cols-[100px_minmax(0,1fr)] sm:gap-6">
          <dt className="font-mono text-[12.5px] text-t1">{k}</dt>
          <dd className="text-[15px] leading-[1.6] text-t2">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
