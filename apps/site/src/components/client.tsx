"use client";

import { useEffect, useSyncExternalStore, type ReactNode } from "react";

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
 *  - `[data-count]` numbers count up from zero when they enter;
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
          if (el.dataset.count !== undefined && !still) countUp(el);
          io.unobserve(el);
        }
      },
      { rootMargin: "0px 0px -12% 0px", threshold: 0.05 },
    );
    const REVEAL = ".fx, .wave, .grow, .typed, [data-count]";
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

/** Animate the first number in an element's text from 0, keeping its prefix, suffix and decimals. */
function countUp(el: HTMLElement) {
  const text = el.textContent ?? "";
  const m = text.match(/(\d+(?:\.\d+)?)/);
  if (!m || m.index === undefined) return;
  const target = Number(m[1]);
  const decimals = m[1].includes(".") ? m[1].split(".")[1].length : 0;
  const head = text.slice(0, m.index);
  const tail = text.slice(m.index + m[1].length);
  const t0 = performance.now();
  const dur = 1100;
  const tick = (t: number) => {
    const k = Math.min(1, (t - t0) / dur);
    const e = 1 - Math.pow(1 - k, 3);
    el.textContent = `${head}${(target * e).toFixed(decimals)}${tail}`;
    if (k < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
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

type Theme = "system" | "dark" | "light";
const THEME_EVENT = "da-theme";
const readTheme = (): Theme => {
  const t = document.documentElement.getAttribute("data-theme");
  return t === "dark" || t === "light" ? t : "system";
};
const subscribeTheme = (cb: () => void) => {
  window.addEventListener(THEME_EVENT, cb);
  return () => window.removeEventListener(THEME_EVENT, cb);
};

/** Auto follows the system setting; Night and Day pin a theme (the boot script in the layout restores it). */
export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribeTheme, readTheme, (): Theme => "system");
  const choose = (t: Theme) => {
    const d = document.documentElement;
    if (t === "system") d.removeAttribute("data-theme");
    else d.setAttribute("data-theme", t);
    try {
      if (t === "system") localStorage.removeItem("da-theme");
      else localStorage.setItem("da-theme", t);
    } catch {
      // storage blocked: the choice still holds for this page view
    }
    window.dispatchEvent(new Event(THEME_EVENT));
  };
  const options: [Theme, string][] = [
    ["system", "Auto"],
    ["dark", "Night"],
    ["light", "Day"],
  ];
  return (
    <div role="group" aria-label="Theme" className="hidden rounded-full border border-line p-0.5 sm:inline-flex">
      {options.map(([t, label]) => (
        <button
          key={t}
          type="button"
          aria-pressed={theme === t}
          onClick={() => choose(t)}
          className={`rounded-full px-2.5 py-1 font-mono text-[10.5px] tracking-[0.03em] transition-colors ${
            theme === t ? "bg-raised text-t1 shadow-[inset_0_0_0_1px_var(--line-2)]" : "text-t3 hover:text-t1"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
