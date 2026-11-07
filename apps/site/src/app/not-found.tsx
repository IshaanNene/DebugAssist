import Link from "next/link";
import { COL, SiteHeader } from "@/components/Chrome";

export default function NotFound() {
  return (
    <>
      <SiteHeader />
      <main className={`${COL} py-32`}>
        <p className="font-mono text-[11px] uppercase tracking-[0.08em] text-t3">404 · no such page</p>
        <h1 className="mt-4 font-display text-[44px] font-medium leading-[1.05] tracking-[-0.03em] text-t1">This page isn’t in the plan.</h1>
        <p className="mt-5 max-w-[520px] text-[16px] leading-[1.6] text-t2">
          The link may point at a record or chapter that was renamed. Every page is listed on the home page.
        </p>
        <Link href="/" className="mt-8 inline-block border border-t1 bg-amber-fill px-4 py-2.5 font-mono text-[12px] text-t1">
          ← Home
        </Link>
      </main>
    </>
  );
}
