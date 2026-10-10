"use client";

import { useEffect, type ReactNode } from "react";

/** A section that rises in as it scrolls into view (CSS scroll-driven; always visible without support). */
export function Reveal({ children, className = "", id }: { children: ReactNode; className?: string; id?: string }) {
  return (
    <section id={id} className={`reveal ${className}`}>
      {children}
    </section>
  );
}

/** Single-key shortcuts shown on the buttons (ignored while typing). */
export function Shortcuts({ map }: { map: Record<string, string> }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      const href = map[e.key.toLowerCase()];
      if (!href) return;
      if (href.startsWith("#")) document.querySelector(href)?.scrollIntoView({ behavior: "smooth" });
      else window.location.href = href;
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [map]);
  return null;
}
