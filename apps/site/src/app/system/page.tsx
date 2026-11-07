import type { Metadata } from "next";
import { Architecture } from "@/components/Architecture";
import { SystemMap } from "@/components/Diagrams";
import { ChapterPage, Figure, Section } from "@/components/Page";
import { facts, writePolicy } from "@/lib/data";
import { adrs, mcpServers } from "@/lib/docs";
import { Markdown } from "@/lib/md";
import Link from "next/link";

export const metadata: Metadata = {
  title: "System — DebugAssist",
  description: "How a signal travels through DebugAssist: read-only evidence servers, a fixed pipeline, and one gate for every write.",
};

const TOC = [
  { id: "map", text: "How a signal travels" },
  { id: "layers", text: "The layers" },
  { id: "servers", text: "Evidence servers" },
  { id: "invariants", text: "Invariants" },
];

// The invariants and the ADR that holds each one; the ADR's title is read from the file.
const INVARIANTS: [string, string, string][] = [
  ["The plan is fixed in code.", "A static graph of ten nodes. Conditional edges exist only where the spec puts them, and are chosen by Clef through policy or by code — never by a model.", "0001"],
  ["Clef decides, the LLM reasons, code acts.", "A model's output never triggers a write directly; it becomes a probability, a policy maps it to an outcome, and deterministic code performs it.", "0002"],
  ["Evidence is collected by code.", "The first bundle is fetched, windowed, deduplicated and scored for relevance to fit a token budget — no model loop. Each item gets a content-hashed evidence ID that claims must cite.", "0003"],
  ["The worktree is hostile input.", "Everything the sandbox can write is treated as untrusted by the host: verified git dirs, no hooks, no symlinks out, credentials never in argv.", "0009"],
  ["A run owns a process.", "Its graph, worktree and run directory belong to it alone. Inside it, per-run values live in task context, never in os.environ; shared files are append-only or atomic.", "0010"],
];

export default function SystemPage() {
  const f = facts();
  const policy = writePolicy();
  const { servers, rules } = mcpServers();
  const records = adrs();
  const writing = servers.filter((s) => s.writes).length;

  return (
    <ChapterPage
      chapter="/system/"
      title={
        <>
          Signals in, evidence up, <span className="hl">one gate out.</span>
        </>
      }
      lead={
        <>
          Agents see the world only through {f.mcpServers} read-only evidence servers. They reason and edit code inside a
          network-less sandbox. Every action that leaves it passes one policy file — and anything that file doesn&apos;t list
          is a dry run.
        </>
      }
      sources={["docs/ARCHITECTURE.md", "docs/mcp.md", "configs/policies/writes.yaml"]}
      toc={TOC}
    >
      <Section id="map" title="How a signal travels" aside="Fig. 1">
        <Figure n="1" title="signals → evidence → pipeline → gate → writes" note="every write passes the gate">
          <SystemMap servers={f.mcpServers} tools={f.mcpTools} templates={f.templates} branchPrefix={policy.branchPrefix} />
        </Figure>
      </Section>

      <Section id="layers" title="The layers" aside="Fig. 2 · hover a layer">
        <Architecture servers={f.mcpServers} tools={f.mcpTools} />
      </Section>

      <Section id="servers" title="Evidence servers" aside={`${servers.length} servers · ${servers.reduce((a, s) => a + s.tools.length, 0)} tools · ${writing} with gated writes`}>
        <div className="fx panel overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse text-left">
            <thead>
              <tr className="border-b border-line bg-sunk/60 font-mono text-[10.5px] uppercase tracking-[0.08em] text-t3">
                <th className="px-5 py-3 font-normal">Server</th>
                <th className="px-5 py-3 font-normal">Backed by</th>
                <th className="px-5 py-3 font-normal">Tools</th>
                <th className="px-5 py-3 text-right font-normal">Writes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {servers.map((s) => (
                <tr key={s.name} className="align-top">
                  <td className="px-5 py-4">
                    <div className="font-mono text-[13px] font-medium text-t1">{s.name}</div>
                    {s.role && <div className="mt-0.5 text-[12px] text-t4">{s.role}</div>}
                  </td>
                  <td className="max-w-[220px] px-5 py-4 text-[13.5px] leading-[1.5] text-t2">{s.backedBy}</td>
                  <td className="px-5 py-4">
                    <div className="flex flex-wrap gap-1">
                      {s.tools.map((t) => (
                        <span key={t} className="border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-t2">
                          {t}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-5 py-4 text-right">
                    {s.writes ? (
                      <span className="inline-block max-w-[180px] border border-t1 px-2 py-0.5 text-left font-mono text-[11px] text-t1">{s.writes.replace(/`/g, "")}</span>
                    ) : (
                      <span className="font-mono text-[11px] text-t4">read-only</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-10 grid gap-10 lg:grid-cols-[260px_minmax(0,1fr)]">
          <div className="fx">
            <div className="label text-[10.5px] text-t4">Every server, every result</div>
            <p className="mt-3 text-[14.5px] leading-[1.6] text-t3">
              The rules in <code className="font-mono text-[12.5px] text-t2">mcp_servers/common.py</code>, which every tool
              result passes before an agent sees it.
            </p>
          </div>
          <div className="fx">
            <Markdown src={rules} from="docs/mcp.md" />
          </div>
        </div>
      </Section>

      <Section id="invariants" title="Invariants" aside="each held by a design record">
        <ol className="border-t border-line">
          {INVARIANTS.map(([t, b, n], i) => {
            const adr = records.find((r) => r.n === n);
            return (
              <li key={n} className="fx grid gap-3 border-b border-line py-6 md:grid-cols-[60px_minmax(0,1fr)_260px]" style={{ ["--i" as string]: i * 0.5 }}>
                <span className="font-mono text-[12px] text-t4">{String(i + 1).padStart(2, "0")}</span>
                <div>
                  <h3 className="text-[19px] font-medium tracking-[-0.015em] text-t1">{t}</h3>
                  <p className="mt-1.5 max-w-[62ch] text-[15px] leading-[1.6] text-t2">{b}</p>
                </div>
                {adr && (
                  <Link href={`/design/${adr.slug}/`} className="group self-start border border-line bg-surface p-3 transition-colors hover:border-line-strong">
                    <span className="font-mono text-[11px] text-t3">ADR {adr.n}</span>
                    <span className="mt-1 block text-[13.5px] leading-[1.4] text-t1">{adr.title}</span>
                  </Link>
                )}
              </li>
            );
          })}
        </ol>
      </Section>
    </ChapterPage>
  );
}
