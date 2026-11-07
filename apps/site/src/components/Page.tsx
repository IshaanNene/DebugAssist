import Link from "next/link";
import type { ReactNode } from "react";
import { COL, SiteFooter, SiteHeader } from "@/components/Chrome";
import { Motion } from "@/components/client";
import { doc } from "@/components/ui";
import { results } from "@/lib/data";
import { CHAPTERS } from "@/lib/chapters";

export { CHAPTERS };


/** A numbered figure in a drafting frame, like a plate in a technical paper. */
export function Figure({ n, title, note, children, className = "" }: { n: string; title: string; note?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <figure className={`fx cbox bg-surface ${className}`}>
      <figcaption className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-4 py-2.5 font-mono text-[11px] text-t3 sm:px-5">
        <span>
          <span className="text-t1">Fig. {n}</span> · {title}
        </span>
        {note && <span className="text-t4">{note}</span>}
      </figcaption>
      <div className="p-4 sm:p-8">{children}</div>
    </figure>
  );
}

/** A section within a page: a mono heading with a rule, then its content. */
export function Section({ id, title, aside, children, className = "" }: { id: string; title: string; aside?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section id={id} className={`scroll-mt-24 pt-24 ${className}`}>
      <div className="fx flex flex-wrap items-baseline justify-between gap-3 border-b border-line-strong pb-3">
        <h2 className="text-[26px] font-medium tracking-[-0.02em] text-t1 sm:text-[30px]">{title}</h2>
        {aside && <div className="font-mono text-[11.5px] text-t3">{aside}</div>}
      </div>
      <div className="mt-8">{children}</div>
    </section>
  );
}

/**
 * A chapter page: the header, a title plate (chapter number, title, lead, source files, contents), the body and a
 * link on to the next chapter.
 */
export function ChapterPage({
  chapter,
  title,
  lead,
  sources,
  toc,
  children,
}: {
  chapter: (typeof CHAPTERS)[number]["href"];
  title: ReactNode;
  lead: ReactNode;
  /** repository paths the page is rendered from */
  sources: string[];
  toc?: { id: string; text: string }[];
  children: ReactNode;
}) {
  const i = CHAPTERS.findIndex((c) => c.href === chapter);
  const c = CHAPTERS[i];
  const next = CHAPTERS[i + 1];
  return (
    <>
      <Motion />
      <SiteHeader />
      <main className={COL}>
        <header className="grid gap-10 border-b border-line pb-14 pt-14 md:pt-20 lg:grid-cols-[minmax(0,1fr)_300px]">
          <div>
            <nav aria-label="Breadcrumb" className="fx font-mono text-[11.5px] uppercase tracking-[0.12em] text-t3">
              <Link href="/" className="hover:text-t1">
                DebugAssist
              </Link>
              <span className="mx-2 text-t4">/</span>
              <span className="text-t1">{c.n}</span> {c.title}
            </nav>
            <h1 className="fx display mt-6 max-w-[18ch] text-[44px] leading-[1.04] text-t1 sm:text-[64px]" style={{ ["--i" as string]: 1 }}>
              {title}
            </h1>
            <p className="fx mt-7 max-w-[60ch] text-[17px] leading-[1.65] text-t2 sm:text-[18.5px]" style={{ ["--i" as string]: 2 }}>
              {lead}
            </p>
          </div>
          <aside className="fx grid content-start gap-6 border-line lg:border-l lg:pl-8" style={{ ["--i" as string]: 3 }}>
            {toc && toc.length > 0 && (
              <div>
                <div className="label text-[10.5px] text-t4">On this page</div>
                <ol className="mt-3 space-y-1.5 text-[14px]">
                  {toc.map((t, k) => (
                    <li key={t.id} className="flex gap-3">
                      <span className="w-5 shrink-0 font-mono text-[11px] leading-[21px] text-t4">{String(k + 1).padStart(2, "0")}</span>
                      <a className="text-t2 hover:text-t1" href={`#${t.id}`}>
                        {t.text}
                      </a>
                    </li>
                  ))}
                </ol>
              </div>
            )}
            <div>
              <div className="label text-[10.5px] text-t4">Rendered from</div>
              <ul className="mt-3 space-y-1.5">
                {sources.map((s) => (
                  <li key={s}>
                    <a href={doc(s)} className="break-all font-mono text-[11.5px] text-t3 underline decoration-line-2 underline-offset-[3px] hover:text-t1">
                      {s}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          </aside>
        </header>

        {children}

        {next && (
          <Link href={next.href} className="group mt-32 grid gap-2 border-y border-line-strong py-8 sm:grid-cols-[120px_minmax(0,1fr)_auto] sm:items-baseline">
            <span className="font-mono text-[11.5px] uppercase tracking-[0.12em] text-t3">Next · {next.n}</span>
            <span>
              <span className="block text-[28px] font-medium tracking-[-0.02em] text-t1 sm:text-[34px]">{next.title}</span>
              <span className="mt-1 block max-w-[60ch] text-[15px] leading-[1.6] text-t3">{next.blurb}</span>
            </span>
            <span className="font-mono text-[20px] text-t1 transition-transform group-hover:translate-x-1">→</span>
          </Link>
        )}
      </main>
      <SiteFooter report={doc(`evals/reports/${results().report}/report.md`)} />
    </>
  );
}
