"use client";

import { useId, useRef, useSyncExternalStore, type CSSProperties, type ReactNode, type ToggleEvent } from "react";
import { createPortal } from "react-dom";
import { doc } from "@/components/ui";

/** Where a figure comes from: a file in the repository (or the local run store), and the row and field read. */
export interface Source {
  file: string;
  row?: string;
  field?: string;
  raw?: string | number;
  note?: string;
}

const noop = () => () => {};
// true once hydrated: the popover is client-only (it lives in <body> so it can sit inside running text)
const useMounted = () => useSyncExternalStore(noop, () => true, () => false);

/**
 * A figure with its receipt. Every number on the site is meant to render through this: tap or focus it to see the
 * file, row, field and raw value it was read from, with a link to the file.
 *
 * Built on the platform: the Popover API gives light dismiss, Escape, the top layer and an accessible invoker;
 * CSS anchor positioning places it, with a measured fallback where that isn't supported.
 */
export function Receipt({ source, children, className = "" }: { source: Source; children: ReactNode; className?: string }) {
  const id = useId().replace(/[^a-zA-Z0-9]/g, "");
  const pop = `receipt-${id}`;
  const anchor = `--receipt-${id}`;
  const btn = useRef<HTMLButtonElement>(null);
  const mounted = useMounted();
  const rows: [string, string | number | undefined][] = [
    ["File", source.file],
    ["Row", source.row],
    ["Field", source.field],
    ["Raw value", source.raw],
  ];

  // Without CSS anchor positioning, place the popover under (or over) its figure, and close it on scroll.
  const place = (e: ToggleEvent<HTMLDivElement>) => {
    if (e.newState !== "open" || !btn.current || CSS.supports("anchor-name: --a")) return;
    const el = e.currentTarget;
    const r = btn.current.getBoundingClientRect();
    const w = el.offsetWidth;
    const h = el.offsetHeight;
    const below = r.bottom + 8 + h <= window.innerHeight - 16 || r.top - h - 8 < 16;
    el.style.left = `${Math.min(Math.max(16, r.left), window.innerWidth - w - 16)}px`;
    el.style.top = `${below ? r.bottom + 8 : r.top - h - 8}px`;
    const close = () => {
      el.hidePopover();
      window.removeEventListener("scroll", close);
    };
    window.addEventListener("scroll", close, { passive: true, once: true });
  };

  return (
    <>
      <button
        ref={btn}
        type="button"
        className={`receipt ${className}`}
        popoverTarget={pop}
        style={{ anchorName: anchor } as CSSProperties}
      >
        {children}
        <span className="sr-only"> (show its source)</span>
      </button>
      {mounted &&
        createPortal(
          <div
            id={pop}
            popover="auto"
            role="dialog"
            aria-label="Receipt"
            onToggle={place}
            className="receipt-pop w-[min(360px,calc(100vw-32px))] rounded-[6px] border border-line-2 bg-raised p-4 text-left text-[13px] text-t1 shadow-[var(--shadow)]"
            style={{ positionAnchor: anchor } as CSSProperties}
          >
            <div className="label text-t3">Receipt</div>
            <dl className="mt-2.5 grid grid-cols-[76px_minmax(0,1fr)] gap-x-3 gap-y-1.5">
              {rows
                .filter(([, v]) => v !== undefined && v !== "")
                .map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="label pt-[3px] text-[10px] text-t3">{k}</dt>
                    <dd className="font-mono text-[12px] leading-[1.5] [overflow-wrap:anywhere]">{String(v)}</dd>
                  </div>
                ))}
            </dl>
            {source.note && <p className="caveat mt-3 border-t border-line pt-2.5 text-[14.5px] text-t2">{source.note}</p>}
            {!source.file.startsWith(".data/") && (
              <a className="mt-3 inline-block text-[12.5px] text-t2 underline underline-offset-[3px] hover:text-t1" href={doc(source.file)}>
                Open the file on GitHub ↗
              </a>
            )}
          </div>,
          document.body,
        )}
    </>
  );
}
