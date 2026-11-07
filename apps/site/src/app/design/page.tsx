import type { Metadata } from "next";
import Link from "next/link";
import { ChapterPage, Section } from "@/components/Page";
import { adrs } from "@/lib/docs";

export const metadata: Metadata = {
  title: "Design records — DebugAssist",
  description: "The architecture decisions behind DebugAssist, each with its context, the decision and its consequences.",
};

export default function DesignIndex() {
  const records = adrs();
  return (
    <ChapterPage
      chapter="/design/"
      title={
        <>
          Why it is built <span className="hl">the way it is.</span>
        </>
      }
      lead={
        <>
          Every decision that shapes the system is written down: the context that forced it, what was
          decided, and what it costs — so the reasoning can be read next to the code it shaped.
        </>
      }
      sources={["docs/adr/"]}
    >
      <Section id="records" title="Records" aside={`${records.length} records · ${records.filter((r) => r.status.startsWith("accepted")).length} accepted`}>
        <ol className="border-t border-line">
          {records.map((r, i) => (
            <li key={r.slug} className="fx" style={{ ["--i" as string]: i * 0.3 }}>
              <Link
                href={`/design/${r.slug}/`}
                className="group grid gap-x-6 gap-y-2 border-b border-line py-6 transition-colors hover:bg-sunk/40 md:grid-cols-[90px_minmax(0,1fr)_150px_24px] md:items-baseline"
              >
                <span className="font-mono text-[13px] text-t1">ADR {r.n}</span>
                <span>
                  <span className="block text-[19px] font-medium leading-[1.3] tracking-[-0.015em] text-t1">{r.title}</span>
                  <span className="mt-1.5 block max-w-[72ch] text-[14.5px] leading-[1.6] text-t3">{r.gist}</span>
                </span>
                <span className="font-mono text-[11.5px] text-t3">
                  {r.status} · {r.date}
                </span>
                <span className="hidden font-mono text-t3 transition-transform group-hover:translate-x-1 group-hover:text-t1 md:block">→</span>
              </Link>
            </li>
          ))}
        </ol>
      </Section>
    </ChapterPage>
  );
}
