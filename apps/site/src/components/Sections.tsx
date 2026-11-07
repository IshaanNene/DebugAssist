import { Receipt } from "@/components/Receipt";
import type { WriteRule } from "@/lib/data";

// The Safety section: the write policy as the agent runs under it, read from configs/policies/writes.yaml at build.

const cx = (...c: (string | false | undefined)[]) => c.filter(Boolean).join(" ");

/* ───────────────────────── Safety ───────────────────────── */

const MODE: Record<string, { label: string; cls: string }> = {
  live: { label: "live", cls: "border-good/50 text-good" },
  approval: { label: "needs approval", cls: "border-amber/60 text-amber" },
  dry_run: { label: "dry run", cls: "border-line-2 text-t3" },
  deny: { label: "never", cls: "border-line-2 text-t3 line-through" },
};

export function Safety({ rules, branchPrefix }: { rules: WriteRule[]; branchPrefix: string }) {
  const file = "configs/policies/writes.yaml";
  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
      <div className="grid content-start gap-3">
        {[
          ["Sandboxed", "Agents work in a container with no network, on a git worktree the host reads only through guards — no symlinks out, no .git, no secrets."],
          ["Bot branches only", `Pushes go only to ${branchPrefix}* branches — never main, release branches or tags.`],
          ["Draft pull requests", "On your repositories, only once the GitHub App is installed and the repo has a .DebugAssist/pipeline.yaml."],
          ["Dry run by default", "Anything the policy does not list is recorded, not performed. Every write that does happen is audited."],
        ].map(([t, b], i) => (
          <div key={t} className="fx panel flex gap-4 p-5" style={{ ["--i" as string]: i }}>
  <span className="mt-1 grid h-6 w-6 shrink-0 place-items-center  bg-tint font-mono text-[11px] text-amber">{i + 1}</span>
            <div>
              <h3 className="text-[16px] font-semibold tracking-[-0.01em] text-t1">{t}</h3>
              <p className="mt-1 text-[14px] leading-[1.55] text-t2">{b}</p>
            </div>
          </div>
        ))}
      </div>
      <div className="fx panel overflow-hidden">
        <div className="flex items-center justify-between gap-3 border-b border-line bg-sunk/60 px-5 py-3">
          <span className="font-mono text-[12px] text-t1">{file}</span>
          <span className="label text-[10px] text-t3">read at build time</span>
        </div>
        <ul className="divide-y divide-line">
          {rules.map((r) => {
            const m = MODE[r.mode] ?? { label: r.mode, cls: "border-line-2 text-t3" };
            return (
              <li key={r.action} className="flex items-center justify-between gap-4 px-5 py-2.5">
                <div className="min-w-0">
                  <div className="font-mono text-[12.5px] text-t1">{r.action}</div>
                  {r.note && <div className="truncate text-[12px] text-t3">{r.note}</div>}
                </div>
                <Receipt source={{ file, field: `actions.${r.action}`, raw: r.mode, note: r.note || undefined }} className="shrink-0 border-b-0">
  <span className={cx("inline-flex  border px-2.5 py-0.5 font-mono text-[11px]", m.cls)}>{m.label}</span>
                </Receipt>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
