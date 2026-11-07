"use client";

import { useEffect, type ReactNode } from "react";

/** A plain section; its entrance is handled by `.fx` children and the Motion observer. */
export function Reveal({ children, className = "", id }: { children: ReactNode; className?: string; id?: string }) {
  return (
    <section id={id} className={className}>
      {children}
    </section>
  );
}

const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * One observer for the whole page, so components stay server-rendered:
 *  - `.fx` / `.wave` elements get `data-in` the first time they enter the viewport (CSS does the motion);
 *  - `[data-scrub="a,b"]` elements get `--p` (0→1) as they travel from a·vh (top) to b·vh (bottom);
 *  - the document gets `--page` (scroll progress) and `data-scrolled`.
 * Server-rendered content is final: without JS (or with reduced motion) everything is simply shown.
 */
export function Motion() {
  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute("data-motion", "");
    const still = reduced();

    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (!e.isIntersecting) continue;
          const el = e.target as HTMLElement;
          el.dataset.in = ""; // an attribute, not a class: React rewrites className on re-render
          io.unobserve(el);
        }
      },
      { rootMargin: "0px 0px -12% 0px", threshold: 0.05 },
    );
    const REVEAL = ".fx, .wave, .grow, .typed";
    const watch = (root: ParentNode) =>
      root.querySelectorAll<HTMLElement>(REVEAL).forEach((el) => {
        if (el.dataset.in === undefined) io.observe(el);
      });
    watch(document);
    // Elements mounted or re-rendered after this ran (a client component remounting, a hydration fix-up, a
    // dev refresh) would otherwise stay hidden for good: watch whatever is added later too.
    const mo = new MutationObserver((records) => {
      for (const r of records)
        for (const node of r.addedNodes) {
          if (!(node instanceof HTMLElement)) continue;
          if (node.matches(REVEAL) && node.dataset.in === undefined) io.observe(node);
          watch(node);
        }
    });
    mo.observe(document.body, { childList: true, subtree: true });

    const scrubs = [...document.querySelectorAll<HTMLElement>("[data-scrub]")];
    let raf = 0;
    const frame = () => {
      raf = 0;
      const vh = window.innerHeight;
      const max = root.scrollHeight - vh;
      root.style.setProperty("--page", max > 0 ? (window.scrollY / max).toFixed(4) : "0");
      root.toggleAttribute("data-scrolled", window.scrollY > 8);
      if (still) return;
      for (const el of scrubs) {
        const [a, b] = (el.dataset.scrub || "1,0").split(",").map(Number);
        const r = el.getBoundingClientRect();
        const p = (vh * a - r.top) / (vh * a - vh * b + r.height);
        el.style.setProperty("--p", Math.min(1, Math.max(0, p)).toFixed(4));
      }
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(frame);
    };
    frame();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      io.disconnect();
      mo.disconnect();
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      cancelAnimationFrame(raf);
    };
  }, []);
  return null;
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
