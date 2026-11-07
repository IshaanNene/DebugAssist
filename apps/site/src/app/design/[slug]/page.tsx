import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { COL, SiteFooter, SiteHeader } from "@/components/Chrome";
import { Motion } from "@/components/client";
import { AdrLayers, AdrRecordFlow } from "@/components/figs";
import { Figure } from "@/components/Page";
import { doc } from "@/components/ui";
import { results } from "@/lib/data";
import { adrs } from "@/lib/docs";
import { Markdown, outline } from "@/lib/md";

export const dynamicParams = false;

export function generateStaticParams() {
  return adrs().map((r) => ({ slug: r.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const r = adrs().find((a) => a.slug === slug);
  return r ? { title: `ADR ${r.n}: ${r.title} — DebugAssist`, description: r.gist } : {};
}

/** One design record, rendered from docs/adr/<slug>.md, with the records either side. */
export default async function AdrPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const all = adrs();
  const i = all.findIndex((a) => a.slug === slug);
  if (i < 0) notFound();
  const r = all[i];
  const prev = all[i - 1];
  const next = all[i + 1];
  const parts = outline(r.body);

  return (
    <>
      <Motion />
      <SiteHeader />
      <main className={COL}>
        <div className="grid gap-12 pt-14 md:pt-20 lg:grid-cols-[220px_minmax(0,720px)] lg:justify-between xl:grid-cols-[240px_minmax(0,760px)_180px]">
          <aside className="font-mono text-[11.5px] lg:sticky lg:top-24 lg:self-start">
            <Link href="/design/" className="uppercase tracking-[0.12em] text-t3 hover:text-t1">
              ← Design records
            </Link>
            <ol className="mt-6 hidden space-y-1 border-l border-line lg:block">
              {all.map((a) => (
                <li key={a.slug}>
                  <Link
                    href={`/design/${a.slug}/`}
                    className={`-ml-px block border-l py-1 pl-3 leading-[1.4] ${a.slug === slug ? "border-t1 text-t1" : "border-transparent text-t3 hover:text-t1"}`}
                  >
                    {a.n}
                  </Link>
                </li>
              ))}
            </ol>
          </aside>

          <article className="min-w-0">
            <div className="fx font-mono text-[12px] text-t3">
              <span className="text-t1">ADR {r.n}</span> · {r.status} · {r.date}
            </div>
            <h1 className="fx display mt-5 text-[36px] leading-[1.1] text-t1 sm:text-[48px]">{r.title}</h1>
            <Figure n="1" title="the record in three lines" note="the first sentence of each section" className="mt-10">
              <div className="p-4 sm:p-6">
                <AdrRecordFlow record={r} w={560} />
              </div>
            </Figure>
            <Figure n="2" title="where it applies" note={`ADR ${r.n}, inked`} className="mt-6">
              <div className="p-4 sm:p-6">
                <AdrLayers records={all} focus={r.n} w={560} />
              </div>
            </Figure>
            <div className="fx mt-12">
              <Markdown src={r.body} from={r.file} skipTitle={false} />
            </div>
            <a href={doc(r.file)} className="mt-10 inline-block font-mono text-[11.5px] text-t3 underline decoration-line-2 underline-offset-[3px] hover:text-t1">
              {r.file}
            </a>

            <nav className="mt-16 grid gap-px border border-line bg-line sm:grid-cols-2">
              {[prev, next].map((a, k) =>
                a ? (
                  <Link key={a.slug} href={`/design/${a.slug}/`} className={`group bg-surface p-5 transition-colors hover:bg-sunk/50 ${k ? "sm:text-right" : ""}`}>
                    <span className="font-mono text-[11px] text-t3">{k ? "Next" : "Previous"} · ADR {a.n}</span>
                    <span className="mt-1 block text-[15px] leading-[1.4] text-t1">{a.title}</span>
                  </Link>
                ) : (
                  <span key={k} className="bg-surface" />
                ),
              )}
            </nav>
          </article>

          <aside className="hidden xl:block xl:sticky xl:top-24 xl:self-start">
            <div className="label text-[10.5px] text-t4">Sections</div>
            <ol className="mt-3 space-y-1.5 text-[13.5px]">
              {parts.map((p) => (
                <li key={p.id}>
                  <a className="text-t3 hover:text-t1" href={`#${p.id}`}>
                    {p.text}
                  </a>
                </li>
              ))}
            </ol>
          </aside>
        </div>
      </main>
      <SiteFooter report={doc(`evals/reports/${results().report}/report.md`)} />
    </>
  );
}
