import Link from "next/link";
import type { ReactNode } from "react";
import { GH, Logo, doc } from "@/components/ui";
import { CHAPTERS } from "@/lib/chapters";

export const COL = "mx-auto w-full max-w-[1240px] px-4 sm:px-8";

// Internal links go through next/link so they keep the GitHub Pages base path.
const NAV: [string, string][] = CHAPTERS.filter((c) => c.nav).map((c) => [c.href, c.title]);

/** The announcement line (optional) and a full-width header bar with the page's scroll progress. */
export function SiteHeader({ banner }: { banner?: ReactNode }) {
  return (
    <>
      {banner}
      <header className="site-header sticky top-0 z-30 border-b border-line bg-surface/95 backdrop-blur-sm">
        <div className={`${COL} flex h-14 items-center justify-between gap-4`}>
          <Link href="/" className="flex items-center gap-2.5 text-[16px] font-semibold tracking-[-0.025em]">
            <Logo />
            DebugAssist
          </Link>
          <nav className="hidden items-center gap-5 text-[13.5px] text-t2 xl:flex">
            {NAV.map(([h, t]) => (
              <Link key={h} className="transition-colors hover:text-t1" href={h}>
                {t}
              </Link>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <details className="group relative">
              <summary className="grid h-8 cursor-pointer list-none place-items-center border border-line-2 px-3 font-mono text-[11.5px] text-t2 hover:text-t1">
                <span className="group-open:hidden">
                  <span className="xl:hidden">Menu</span>
                  <span className="hidden xl:inline">All pages</span>
                </span>
                <span className="hidden group-open:inline">Close</span>
              </summary>
              <nav className="absolute right-0 top-10 z-40 w-[280px] border border-line-strong bg-surface py-2">
                {CHAPTERS.map((c) => (
                  <Link key={c.href} href={c.href} className="flex gap-3 px-4 py-2 text-[14px] text-t2 hover:bg-sunk hover:text-t1">
                    <span className="font-mono text-[11px] leading-[21px] text-t4">{c.n}</span>
                    {c.title}
                  </Link>
                ))}
              </nav>
            </details>
            <a
              href={GH}
              className="inline-flex h-8 items-center gap-2.5 border border-t1 bg-t1 px-3 text-[13.5px] font-medium text-surface transition-colors hover:bg-t2"
            >
              <GitHubMark size={14} />
              GitHub
              <kbd className="hidden h-[18px] min-w-[18px] place-items-center border border-surface/25 px-1 font-mono text-[10.5px] text-surface/80 sm:grid">G</kbd>
            </a>
          </div>
        </div>
        <div aria-hidden className="progress absolute inset-x-0 -bottom-px h-px bg-t1" />
      </header>
    </>
  );
}

export function GitHubMark({ size = 16 }: { size?: number }) {
  return (
    <svg aria-hidden width={size} height={size} viewBox="0 0 16 16" fill="currentColor">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}

/** A one-line announcement above the header. */
export function Banner({ href, tag, children }: { href: string; tag: string; children: ReactNode }) {
  return (
    <Link href={href} className="group block border-b border-line bg-sunk/60 px-4 py-2 text-center text-[13px] text-t2 transition-colors hover:text-t1">
      <span className="mr-2.5 inline-flex h-5 items-center bg-t1 px-1.5 font-mono text-[10.5px] font-medium uppercase tracking-[0.06em] text-surface">
        new
      </span>
      <span className="font-mono text-[11.5px] uppercase tracking-[0.06em] text-t3">{tag}</span> · {children}{" "}
      <span className="inline-block transition-transform group-hover:translate-x-0.5">→</span>
    </Link>
  );
}

export function SiteFooter({ report }: { report: string }) {
  return (
    <footer className="relative mt-[160px] overflow-hidden">
      <div className="horizon" />
      <div className={`${COL} grid gap-10 py-16 text-[13.5px] md:grid-cols-[1.6fr_1fr_1fr_1fr_1fr]`}>
        <div>
          <div className="flex items-center gap-2.5 text-[16px] font-semibold tracking-[-0.025em]">
            <Logo />
            DebugAssist
          </div>
          <p className="mt-4 max-w-[34ch] leading-[1.6] text-t3">
            An open-source on-call engineer. MIT licensed, built and measured in the open.
          </p>
        </div>
        <FooterCol title="Site" links={CHAPTERS.map((c) => [c.title, c.href])} internal />
        <FooterCol title="Project" links={[["GitHub", GH], ["README", doc("README.md")], ["Latest report", report]]} />
        <FooterCol title="Docs" links={[["Architecture", doc("docs/ARCHITECTURE.md")], ["MCP servers", doc("docs/mcp.md")], ["Lessons learned", doc("docs/LESSONS.md")]]} />
        <FooterCol title="Process" links={[["Decision records", `${GH}/tree/main/docs/adr`], ["Roadmap", doc("docs/ROADMAP.md")], ["Progress", doc("docs/PROGRESS.md")]]} />
      </div>
      <div className="border-t border-line">
        <div className={`${COL} py-5 text-[12px] leading-[1.6] text-t4`}>
          Not affiliated with Uber, Cloudflare, OpenAI, OpenRouter, Groq or any company named here; names indicate
          integrations only.
        </div>
      </div>
    </footer>
  );
}

function FooterCol({ title, links, internal }: { title: string; links: [string, string][]; internal?: boolean }) {
  return (
    <div>
      <div className="label text-[10.5px] text-t4">{title}</div>
      <ul className="mt-4 space-y-2.5">
        {links.map(([t, h]) => (
          <li key={t}>
            {internal ? (
              <Link className="text-t2 transition-colors hover:text-t1" href={h}>
                {t}
              </Link>
            ) : (
              <a className="text-t2 transition-colors hover:text-t1" href={h}>
                {t}
              </a>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
