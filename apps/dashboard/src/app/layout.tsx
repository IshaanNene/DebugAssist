import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "DebugAssist",
  description: "Crash or bug report → root cause → validated fix",
};

// Every page reads live run data.
export const dynamic = "force-dynamic";

const NAV = [
  { href: "/", label: "Inbox" },
  { href: "/runs", label: "Runs" },
  { href: "/chat", label: "Chat" },
  { href: "/metrics", label: "Metrics" },
  { href: "/marketplace", label: "Marketplace" },
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex min-h-full font-sans">
        <nav className="sticky top-0 flex h-screen w-48 shrink-0 flex-col gap-1 border-r border-line bg-panel p-4">
          <Link href="/" className="mb-4 text-lg font-bold">
            Debug<span className="text-llm">Assist</span>
          </Link>
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} className="rounded px-2 py-1.5 text-sm hover:bg-bg">
              {n.label}
            </Link>
          ))}
          <div className="mt-auto space-y-1 text-xs text-muted">
            <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-det" /> deterministic</div>
            <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-llm" /> LLM</div>
            <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-clef" /> Clef decision</div>
          </div>
        </nav>
        <main className="min-w-0 flex-1 p-6">{children}</main>
      </body>
    </html>
  );
}
