import type { Metadata } from "next";
import Link from "next/link";
import { Draw } from "@/components/Draw";
import { ChapterPage, Figure, Section } from "@/components/Page";
import { ShipGraph } from "@/components/figs";
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

// The system as docs/ARCHITECTURE.md describes it: client → gateway (GraphQL) → dispatch and payments; Postgres
// behind Toxiproxy; flags from Unleash; every component ships OpenTelemetry to the collector, which feeds Jaeger,
// Loki and Prometheus. Below xl the components table stands in for it.
function MiniRideMap() {
  return (
    <Draw
      w={1200}
      h={390}
      legend={false}
      boxes={[
        { x: 0, y: 40, w: 220, h: 120, title: "client", tag: "TS · React 19", lines: ["booking · notifications", "push links · ETA poller"] },
        { x: 300, y: 40, w: 220, h: 120, title: "gateway", tag: "Node 22", lines: ["GraphQL Yoga · rider API", "logs every operation"] },
        { x: 600, y: 0, w: 220, h: 90, title: "dispatch", tag: "Python 3.13", lines: ["FastAPI"] },
        { x: 600, y: 110, w: 220, h: 90, title: "payments", tag: "Go", lines: ["per-city tariffs"] },
        { x: 900, y: 0, w: 300, h: 90, title: "Postgres", lines: ["behind Toxiproxy"], shape: "store" },
        { x: 900, y: 110, w: 300, h: 90, title: "Unleash", lines: ["notif_router_v2 · surge_pricing"], shape: "store" },
        { x: 0, y: 280, w: 840, h: 100, title: "OpenTelemetry collector", lines: ["W3C trace context browser → gateway → dispatch / payments · x-session-id · x-app-version"], tone: "ink" },
        { x: 900, y: 280, w: 300, h: 100, title: "Jaeger · Loki · Prometheus", lines: ["traces · logs · metrics"], shape: "store" },
      ]}
      edges={[
        { d: "M220 100 H 300" },
        { d: "M520 80 H 560 V 45 H 600" },
        { d: "M520 120 H 560 V 155 H 600" },
        { d: "M820 45 H 900" },
        { d: "M820 155 H 900" },
        { d: "M110 160 V 280", dashed: true },
        { d: "M410 160 V 280", dashed: true },
        { d: "M710 200 V 280", dashed: true },
        { d: "M840 330 H 900" },
      ]}
      labels={[
        { x: 260, y: 84, text: "GraphQL", boxed: false },
        { x: 560, y: 240, text: "OTLP from every component", boxed: false },
      ]}
      steps={[]}
    />
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
          <div className="xl:hidden">{components && <Table t={components} from={ARCH} />}</div>
        </Figure>
        <div className="mt-8 hidden xl:block">{components && <Table t={components} from={ARCH} wide={900} />}</div>
        <div className="fx mt-8 max-w-[80ch]">
          <Markdown src={contract} from={ARCH} />
        </div>
      </Section>

      <Section id="standins" title="Stand-ins for production" aside="what each internal tool becomes here">
        {standins && <Table t={standins} from={ARCH} wide={720} />}
      </Section>

      <Section id="inject" title="Shipping a bug" aside="debugassist scenario inject · trigger">
        <Figure n="2" title="one catalog bug, as git sees it" note={`${ARCH} › Bug catalog and scenarios`} className="mb-10">
          <ShipGraph />
        </Figure>
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
