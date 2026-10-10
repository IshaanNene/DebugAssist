"use client";

import { useEffect, useState, type ReactNode } from "react";
import type { FeaturedRun } from "@/lib/data";

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
 *  - `.fx` / `.wave` elements get `.in` the first time they enter the viewport (CSS does the motion);
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
          el.classList.add("in");
          if (el.dataset.count !== undefined && !still) countUp(el);
          io.unobserve(el);
        }
      },
      { rootMargin: "0px 0px -12% 0px", threshold: 0.05 },
    );
    document.querySelectorAll<HTMLElement>(".fx, .wave, .grow, .typed, [data-count]").forEach((el) => io.observe(el));

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
    const onPointer = (e: PointerEvent) => {
      const card = (e.target as HTMLElement | null)?.closest<HTMLElement>(".spot");
      if (!card) return;
      const r = card.getBoundingClientRect();
      card.style.setProperty("--mx", `${e.clientX - r.left}px`);
      card.style.setProperty("--my", `${e.clientY - r.top}px`);
    };
    frame();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    document.addEventListener("pointermove", onPointer, { passive: true });
    return () => {
      document.removeEventListener("pointermove", onPointer);
      io.disconnect();
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

type Kind = "code" | "llm" | "clef" | "ok";
interface Line {
  step: string;
  kind: Kind;
  text: ReactNode;
}

const DOT: Record<Kind, string> = { code: "#cfcfc9", llm: "#8b7cf0", clef: "#e0901b", ok: "#3f8f4f" };

/** The hero card: one real baseline run from the report, replayed line by line, on a loop. */
export function LiveRun({ run, model }: { run: FeaturedRun; model: string }) {
  const lines: Line[] = [
    { step: "ingest", kind: "code", text: <>{run.issue} · {run.agentType}</> },
    { step: "triage", kind: "clef", text: <>priority by Clef · owner from CODEOWNERS</> },
    { step: "context", kind: "code", text: <>evidence bundle from the MCP servers</> },
    {
      step: "root cause",
      kind: "llm",
      text: (
        <>
          <span className="text-t1">{run.location}</span>
        </>
      ),
    },
    {
      step: "grounding",
      kind: "code",
      text: (
        <>
          {run.claims} claims · {run.unsupported} unsupported
        </>
      ),
    },
    { step: "reproduce", kind: "llm", text: <>{run.tier} test fails on the shipped release</> },
    { step: "fix", kind: "llm", text: <>test passes · suite green</> },
    {
      step: "hidden test",
      kind: "ok",
      text: (
        <>
          <span className="text-good">passed</span> · {run.hiddenTest.split("/").pop()}
        </>
      ),
    },
  ];
  const [n, setN] = useState(lines.length);
  useEffect(() => {
    if (reduced()) return;
    let i = 0;
    const reset = setTimeout(() => setN(0), 0); // server-rendered complete; replay from the start
    const t = setInterval(() => {
      i += 1;
      if (i > lines.length + 6) i = 0; // hold the finished run for a moment, then replay
      setN(Math.min(i, lines.length));
    }, 650);
    return () => {
      clearTimeout(reset);
      clearInterval(t);
    };
  }, [lines.length]);
  const done = n >= lines.length;

  return (
    <div className="cbox float-card bg-[#fdfdfb] shadow-[0_30px_60px_-30px_rgba(40,38,30,0.35)]">
      <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
        <div className="flex items-center gap-2 font-mono text-[11px] text-t3">
          <span className={`inline-block h-2 w-2 rounded-full ${done ? "bg-good" : "pulse bg-[#e0901b]"}`} />
          {done ? "run finished" : "running"} · {run.bug}
        </div>
        <span className="font-mono text-[10.5px] text-t4">{model}</span>
      </div>
      <ol className="space-y-0 px-4 py-3 font-mono text-[12px] leading-[1.5]">
        {lines.map((l, i) => (
          <li
            key={l.step}
            className={`grid grid-cols-[14px_92px_1fr] items-start gap-2 py-[5px] transition-all duration-300 ${
              i < n ? "translate-y-0 opacity-100" : "translate-y-1 opacity-0"
            }`}
          >
            <span className="mt-[5px] inline-block h-2 w-2 rounded-full border border-t2" style={{ background: DOT[l.kind] }} />
            <span className="text-t3">{l.step}</span>
            <span className="min-w-0 break-words text-t2">
              {l.text}
              {i === n - 1 && !done && <span className="caret" />}
            </span>
          </li>
        ))}
      </ol>
      <div className="grid grid-cols-3 border-t border-line font-mono text-[11px]">
        {[
          ["cost", `$${run.usd.toFixed(3)}`],
          ["agent turns", String(run.turns)],
          ["wall time", `${Math.round(run.wallS)} s`],
        ].map(([k, v], i) => (
          <div key={k} className={`px-4 py-2.5 ${i ? "border-l border-line" : ""}`}>
            <div className="text-t4">{k}</div>
            <div className={`mt-0.5 text-[13px] transition-opacity duration-500 ${done ? "text-t1 opacity-100" : "opacity-30"}`}>{v}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
