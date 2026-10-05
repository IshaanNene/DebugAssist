import type { Decision } from "@/lib/types";
import { Badge } from "./ui";

const BAND = { act: "green", escalate: "amber", safe_default: "gray", per_item: "blue" } as const;

function Bar({ p, lo, hi }: { p: number; lo?: number; hi?: number }) {
  return (
    <div className="relative h-2 w-40 rounded bg-line" title={`p=${p.toFixed(3)}${hi != null ? ` · act ≥ ${hi} · safe default < ${lo}` : ""}`}>
      <div className="h-2 rounded bg-clef" style={{ width: `${Math.max(0, Math.min(1, p)) * 100}%` }} />
      {lo != null && <div className="absolute top-[-3px] h-3.5 w-px bg-muted" style={{ left: `${lo * 100}%` }} />}
      {hi != null && <div className="absolute top-[-3px] h-3.5 w-px bg-ink" style={{ left: `${hi * 100}%` }} />}
    </div>
  );
}

function chosenText(d: Decision): string {
  return Object.entries(d.chosen)
    .filter(([k]) => !k.startsWith("is_location."))
    .slice(0, 4)
    .map(([k, v]) => `${k}: ${typeof v === "number" ? v.toFixed(2) : String(v)}`)
    .join(" · ");
}

export function DecisionLedger({ decisions }: { decisions: Decision[] }) {
  if (decisions.length === 0) return <p className="text-sm text-muted">No decisions recorded for this run.</p>;
  return (
    <ul className="divide-y divide-line">
      {decisions.map((d) => (
        <li key={d.id} className="py-2">
          <details>
            <summary className="flex cursor-pointer flex-wrap items-center gap-2 text-sm">
              <span className="w-40 shrink-0 font-mono text-xs">{d.decision_id}</span>
              {d.confidence >= 0 ? <Bar p={d.confidence} lo={d.policy?.tau_low} hi={d.policy?.tau_high} /> : <span className="w-40 truncate text-xs text-muted" title={chosenText(d)}>{chosenText(d) || "per item"}</span>}
              <Badge tone={BAND[d.band as keyof typeof BAND] ?? "gray"}>{d.band}</Badge>
              <span className="font-medium">{d.action}</span>
              <span className="ml-auto text-xs text-muted">
                {d.backend}
                {d.fallback_reason && " (fallback)"} · {d.latency_ms}ms · ${d.cost_usd.toFixed(5)}
              </span>
            </summary>
            <div className="mt-2 space-y-1 pl-2 text-xs">
              {d.description && <p className="text-muted">{d.description}</p>}
              <p>{chosenText(d)}</p>
              {d.policy && (
                <p className="text-muted">
                  policy on <span className="font-mono">{d.policy.question}</span>: act ≥ {d.policy.tau_high}, safe default &lt; {d.policy.tau_low}
                </p>
              )}
              {Object.entries(d.questions).slice(0, 3).map(([q, spec]) => (
                <p key={q} className="text-muted">
                  <span className="font-mono">{q}</span>: {spec.instructions?.slice(0, 220)}
                </p>
              ))}
              {d.fallback_reason && <p className="text-amber-600">fallback: {d.fallback_reason}</p>}
            </div>
          </details>
        </li>
      ))}
    </ul>
  );
}
