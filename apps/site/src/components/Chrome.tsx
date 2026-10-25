import Link from "next/link";
import type { ReactNode } from "react";
import { ThemeToggle } from "@/components/client";
import { Button, GH, Logo, doc } from "@/components/ui";

export const COL = "mx-auto w-full max-w-[1200px] px-4 sm:px-8";

// Internal links go through next/link so they keep the GitHub Pages base path.
const NAV: [string, string][] = [
  ["/#how", "How it works"],
  ["/#architecture", "Architecture"],
  ["/#results", "Results"],
  ["/#safety", "Safety"],
  ["/results/", "Lab notebook"],
  ["/#faq", "FAQ"],
];

/** The announcement line (optional) and the sticky header with the page's scroll progress in amber. */
export function SiteHeader({ banner }: { banner?: ReactNode }) {
  return (
    <>
      {banner}
      <header className="site-header sticky top-0 z-30 border-b border-line bg-surface/80 backdrop-blur-md">
        <div className={`${COL} flex h-14 items-center justify-between gap-4`}>
          <Link href="/" className="flex items-center gap-2.5 text-[15px] font-semibold tracking-[-0.02em] [font-stretch:110%]">
            <Logo />
            DebugAssist
          </Link>
          <nav className="hidden gap-6 text-[13px] text-t3 lg:flex">
            {NAV.map(([h, t]) => (
              <Link key={h} className="relative py-1 transition-colors hover:text-t1" href={h}>
                {t}
              </Link>
            ))}
          </nav>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <Button href={GH} hint="G">
              GitHub
            </Button>
          </div>
        </div>
        <div aria-hidden className="progress absolute inset-x-0 -bottom-px h-[2px] bg-amber" />
      </header>
    </>
  );
}

/** A one-line announcement above the header. */
export function Banner({ href, tag, children }: { href: string; tag: string; children: ReactNode }) {
  return (
    <Link href={href} className="group block border-b border-line bg-raised px-4 py-2 text-center text-[12.5px] text-t2 hover:text-t1">
      <span className="mr-2 inline-flex h-[18px] items-center rounded-[3px] bg-amber-fill px-1.5 font-mono text-[10px] font-medium uppercase tracking-[0.05em] text-ink">
        new
      </span>
      <span className="label mr-1 text-[10.5px] text-t3">{tag}</span> · {children}{" "}
      <span className="inline-block transition-transform group-hover:translate-x-0.5">→</span>
    </Link>
  );
}

export function SiteFooter({ report }: { report: string }) {
  return (
    <footer className="mt-[140px] overflow-hidden border-t border-line">
      <div className={`${COL} grid gap-8 py-12 text-[12.5px] sm:grid-cols-4`}>
        <div className="sm:col-span-1">
          <div className="flex items-center gap-2 text-[14px] font-semibold [font-stretch:110%]">
            <Logo size={18} />
            DebugAssist
          </div>
          <p className="mt-2 text-t3">MIT licensed, independent open-source project.</p>
        </div>
        <FooterCol title="Project" links={[["GitHub", GH], ["README", doc("README.md")], ["Latest report", report]]} />
        <FooterCol title="Docs" links={[["Lessons learned", doc("docs/LESSONS.md")], ["Roadmap", doc("docs/ROADMAP.md")], ["MCP servers", doc("docs/mcp.md")]]} />
        <FooterCol title="Process" links={[["Architecture", doc("docs/ARCHITECTURE.md")], ["Decisions", `${GH}/tree/main/docs/adr`], ["Progress", doc("docs/PROGRESS.md")]]} />
      </div>
      <div className="border-t border-line">
        <div className={`${COL} py-4 text-[11.5px] text-t3`}>
          Not affiliated with Uber, Cloudflare, OpenAI, OpenRouter, Groq or any company named here; names indicate
          integrations only.
        </div>
      </div>
    </footer>
  );
}

function FooterCol({ title, links }: { title: string; links: [string, string][] }) {
  return (
    <div>
      <div className="label text-[10.5px] text-t3">{title}</div>
      <ul className="mt-2 space-y-1.5">
        {links.map(([t, h]) => (
          <li key={t}>
            <a className="text-t2 hover:text-t1" href={h}>
              {t}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
