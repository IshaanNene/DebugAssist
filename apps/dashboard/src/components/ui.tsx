import type { ReactNode } from "react";

export function Card({ title, children, right }: { title?: ReactNode; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="rounded-lg border border-line bg-panel p-4">
      {(title || right) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">{title}</h2>
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

const TONES: Record<string, string> = {
  red: "bg-red-500/15 text-red-600 dark:text-red-400",
  amber: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  green: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  blue: "bg-blue-500/15 text-blue-700 dark:text-blue-400",
  gray: "bg-zinc-500/15 text-zinc-600 dark:text-zinc-300",
};

export function Badge({ tone = "gray", children, title }: { tone?: keyof typeof TONES; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${TONES[tone]}`}>
      {children}
    </span>
  );
}

export function priorityTone(p: string | null | undefined): keyof typeof TONES {
  return p === "P0" || p === "P1" ? "red" : p === "P2" ? "amber" : "gray";
}

export function outcomeTone(o: string | null | undefined): keyof typeof TONES {
  if (o === "open_pr" || o === "resolved" || o === "done") return "green";
  if (o === "draft_pr" || o === "watching" || o === "running") return "blue";
  if (o === "failed" || o === "escalate" || o === "reopened") return "red";
  return "gray";
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-lg border border-dashed border-line p-6 text-sm text-muted">{children}</p>;
}

export function ApiDown() {
  return (
    <Empty>
      The DebugAssist API is not reachable. Start it with <code className="font-mono">make dashboard</code> (API on
      :8400, dashboard on :3000).
    </Empty>
  );
}

export function pct(p: number | null | undefined): string {
  return p == null ? "–" : `${Math.round(p * 100)}%`;
}

export function when(iso: string | null | undefined): string {
  if (!iso) return "–";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

// Inline `code` spans in RCA text (the agents write markdown-ish prose).
export function Prose({ text }: { text: string }) {
  const parts = text.split(/(`[^`]+`)/g);
  return (
    <>
      {parts.map((p, i) =>
        p.startsWith("`") && p.endsWith("`") && p.length > 2 ? (
          <code key={i} className="rounded bg-bg px-1 font-mono text-[0.85em]">{p.slice(1, -1)}</code>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </>
  );
}
