import type { ReactNode } from "react";

export const GH = "https://github.com/IshaanNene/DebugAssist";
export const doc = (p: string) => `${GH}/blob/main/${p}`;

const cx = (...c: (string | false | undefined)[]) => c.filter(Boolean).join(" ");

/** A bordered cell with 8px corner brackets. `stack` hides brackets where cells share a border. */
export function Box({
  children,
  className,
  stack,
  stripes,
}: {
  children?: ReactNode;
  className?: string;
  stack?: "first" | "middle" | "last";
  stripes?: boolean;
}) {
  return (
    <div
      className={cx(
        "cbox",
        stack === "first" && "no-bottom",
        stack === "middle" && "no-top no-bottom -mt-px",
        stack === "last" && "no-top -mt-px",
        stripes && "stripes",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** A highlighter stroke behind a phrase (multiply blend, like ink on paper). */
export function Mark({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={cx("relative inline-flex items-center", className)}>
      <span aria-hidden className="absolute inset-x-[-0.06em] top-1/2 h-[0.74em] -translate-y-[50%] bg-mark mix-blend-multiply" />
      <span className="relative">{children}</span>
    </span>
  );
}

export function H2({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <h2
      className={cx(
        "font-display font-medium text-t1 tracking-[-0.02em] text-[32px] sm:text-[42px] md:text-[48px] leading-[1.04]",
        className,
      )}
    >
      {children}
    </h2>
  );
}

export function Lead({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cx("text-[15px] leading-[1.55] tracking-[-0.005em] text-t3 max-w-[52ch]", className)}>{children}</p>;
}

export function Label({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cx("font-mono text-[11px] uppercase tracking-[0.04em] text-t3", className)}>{children}</span>;
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
        "inline-flex h-8 items-center gap-2 border px-3 text-[12.5px] font-[460] tracking-[-0.005em] shadow-[0_1px_0_rgba(0,0,0,0.04)] transition-colors",
        primary ? "border-t2 bg-t1 text-surface hover:bg-t2" : "border-line bg-surface text-t2 hover:border-line-strong",
      )}
    >
      {children}
      {hint && (
        <kbd
          className={cx(
            "grid h-[18px] min-w-[18px] place-items-center px-1 font-mono text-[10px] not-italic",
            primary ? "border border-white/20 bg-white/15 text-surface" : "border border-black/15 bg-black/[0.06] text-t3",
          )}
        >
          {hint}
        </kbd>
      )}
    </a>
  );
}

export function Dot() {
  return <span aria-hidden className="inline-block h-[3px] w-[3px] bg-t4" />;
}

export function Chip({ children, tone }: { children: ReactNode; tone?: "good" | "bad" | "muted" }) {
  return (
    <span
      className={cx(
        "inline-flex items-center border bg-surface px-2 py-[3px] font-mono text-[11px] leading-none",
        tone === "good" ? "border-good/40 text-good" : tone === "bad" ? "border-bad/40 text-bad" : "border-line text-t2",
      )}
    >
      {children}
    </span>
  );
}
