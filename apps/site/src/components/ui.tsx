import type { ReactNode } from "react";

export const GH = "https://github.com/IshaanNene/DebugAssist";
export const doc = (p: string) => `${GH}/blob/main/${p}`;

const cx = (...c: (string | false | undefined)[]) => c.filter(Boolean).join(" ");

/** The mark: a signal that spikes once and settles, on an ink square. */
export function Logo({ size = 22 }: { size?: number }) {
  return (
    <span aria-hidden className="grid shrink-0 place-items-center bg-t1" style={{ width: size, height: size }}>
      <svg width={size * 0.68} height={size * 0.68} viewBox="0 0 14 14">
        <path d="M1 8.5h2.6l1.7-5.5 2.4 8.5 1.6-4.2H13" fill="none" stroke="var(--bg)" strokeWidth={1.6} strokeLinejoin="miter" strokeLinecap="square" />
      </svg>
    </span>
  );
}

/** A section's small heading line: a numbered index and a name, like a figure in a paper. */
export function Eyebrow({ n, children, className }: { n?: string; children: ReactNode; className?: string }) {
  return (
    <div className={cx("fx flex items-center gap-3 font-mono text-[11.5px] uppercase tracking-[0.12em] text-t3", className)}>
      {n && <span className="text-amber">{n}</span>}
      {n && <span aria-hidden className="h-px w-8 bg-line-2" />}
      {children}
    </div>
  );
}

/** A raised surface for one self-contained block (a table, a chart, a list of links). */
export function Panel({ children, className }: { children?: ReactNode; className?: string }) {
  return <div className={cx("panel", className)}>{children}</div>;
}

export function H2({ children, className }: { children: ReactNode; className?: string }) {
  return <h2 className={cx("fx title text-t1 text-[38px] sm:text-[52px] md:text-[64px]", className)}>{children}</h2>;
}

export function Lead({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p className={cx("fx max-w-[58ch] text-[17px] leading-[1.65] text-t2 sm:text-[18.5px]", className)} style={{ ["--i" as string]: 1 }}>
      {children}
    </p>
  );
}

export function Label({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cx("label text-t3", className)}>{children}</span>;
}

export function Button({
  href,
  children,
  hint,
  variant = "secondary",
}: {
  href: string;
  children: ReactNode;
  hint?: string;
  variant?: "primary" | "secondary";
}) {
  const primary = variant === "primary";
  return (
    <a
      href={href}
      className={cx(
        "inline-flex h-10 items-center gap-3 border px-4 text-[14.5px] font-medium tracking-[-0.01em] shadow-[0_1px_0_var(--line)] transition-colors active:translate-y-px",
        primary ? "border-t1 bg-t1 text-surface hover:bg-t2" : "border-line-2 bg-surface text-t1 hover:border-line-strong",
      )}
    >
      {children}
      {hint && (
        <kbd
          className={cx(
            "grid h-5 min-w-5 place-items-center border px-1 font-mono text-[11px] font-medium not-italic",
            primary ? "border-surface/25 text-surface/80" : "border-line-2 text-t3",
          )}
        >
          {hint}
        </kbd>
      )}
    </a>
  );
}

export function Dot() {
  return <span aria-hidden className="inline-block h-[3px] w-[3px] rounded-full bg-t4" />;
}

export function Chip({ children, tone }: { children: ReactNode; tone?: "good" | "bad" | "muted" }) {
  return (
    <span
      className={cx(
  "inline-flex items-center  border bg-raised px-2 py-[3px] font-mono text-[11px] leading-none",
        tone === "good" ? "border-good/40 text-good" : tone === "bad" ? "border-line-2 text-bad" : "border-line text-t2",
      )}
    >
      {children}
    </span>
  );
}
