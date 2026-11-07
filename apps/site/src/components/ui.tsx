import type { ReactNode } from "react";

export const GH = "https://github.com/IshaanNene/DebugAssist";
export const doc = (p: string) => `${GH}/blob/main/${p}`;

const cx = (...c: (string | false | undefined)[]) => c.filter(Boolean).join(" ");

/** The mark: a signal that spikes once and settles, on amber. */
export function Logo({ size = 20 }: { size?: number }) {
  return (
    <span aria-hidden className="grid shrink-0 place-items-center rounded-[4px] bg-amber-fill" style={{ width: size, height: size }}>
      <svg width={size * 0.64} height={size * 0.64} viewBox="0 0 14 14">
        <path
          d="M1 9.5h3l1.6-6 2.2 8.5 1.4-4H13"
          fill="none"
          stroke="var(--ink)"
          strokeWidth={1.6}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      </svg>
    </span>
  );
}

/** A raised surface for one self-contained block (a table, a chart, a list of links). */
export function Panel({ children, className }: { children?: ReactNode; className?: string }) {
  return <div className={cx("panel", className)}>{children}</div>;
}

export function H2({ children, className }: { children: ReactNode; className?: string }) {
  return <h2 className={cx("fx title text-t1 text-[34px] sm:text-[44px] md:text-[54px]", className)}>{children}</h2>;
}

export function Lead({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p className={cx("fx max-w-[60ch] text-[17px] leading-[1.6] text-t2", className)} style={{ ["--i" as string]: 1 }}>
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
        "inline-flex h-9 items-center gap-2.5 rounded-[5px] border px-3.5 text-[13.5px] font-semibold tracking-[-0.005em] transition-[background-color,border-color,transform] duration-150 active:translate-y-px",
        primary
          ? "border-transparent bg-amber-fill text-ink hover:brightness-105"
          : "border-line-2 bg-raised text-t1 hover:border-line-strong",
      )}
    >
      {children}
      {hint && (
        <kbd
          className={cx(
            "grid h-[18px] min-w-[18px] place-items-center rounded-[3px] border px-1 font-mono text-[10px] font-medium not-italic",
            primary ? "border-ink/30 text-ink/80" : "border-line-2 text-t3",
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
        "inline-flex items-center rounded-[3px] border bg-raised px-2 py-[3px] font-mono text-[11px] leading-none",
        tone === "good" ? "border-good/40 text-good" : tone === "bad" ? "border-line-2 text-bad" : "border-line text-t2",
      )}
    >
      {children}
    </span>
  );
}
