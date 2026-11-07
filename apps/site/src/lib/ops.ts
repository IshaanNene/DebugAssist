// Build-time numbers for the Cost and latency and the Limitations pages. Every value is computed here from the
// generated reports (evals/reports/<date>/*.csv) or read from configs/ — never typed by hand.
import fs from "node:fs";
import path from "node:path";
import { parseCsv, REPORTS, ROOT, type Results, type Row } from "@/lib/data";

/** Nearest-rank percentile of a list (q in 0..1). */
export function pct(xs: number[], q: number): number {
  if (!xs.length) return 0;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.max(0, Math.ceil(q * s.length) - 1))];
}

/** Wilson score interval (95%) for k successes out of n. */
export function wilson(k: number, n: number): [number, number] {
  if (!n) return [0, 0];
  const z = 1.96;
  const p = k / n;
  const d = 1 + (z * z) / n;
  const c = (p + (z * z) / (2 * n)) / d;
  const h = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / d;
  return [Math.max(0, c - h), Math.min(1, c + h)];
}

const num = (rs: Row[], k: string) => rs.map((r) => r[k]).filter((v) => v !== "" && v !== undefined).map(Number).filter(Number.isFinite);

export interface Dist {
  n: number;
  p50: number;
  p90: number;
  max: number;
}
const dist = (xs: number[]): Dist => ({ n: xs.length, p50: pct(xs, 0.5), p90: pct(xs, 0.9), max: xs.length ? Math.max(...xs) : 0 });

export interface Economics {
  runs: number;
  bugs: number;
  usd: Dist;
  total: number;
  llmShare: number; // of all spend
  perRun: { bug: string; seed: string; llm: number; clef: number; usd: number }[]; // sorted by cost
  toRca: Dist; // seconds, discovery → root cause
  toEnd: Dist; // seconds, discovery → the run's last step
  pipeline: Dist; // seconds the pipeline ran
  turns: Dist;
}

/** Cost and time of the headline runs (each bug's latest full-strength run). */
export function economics(data: Results): Economics {
  const rs = data.runs;
  const perRun = rs
    .map((r) => ({ bug: r.bug, seed: r.seed, llm: Number(r.llm_usd) || 0, clef: Number(r.clef_usd) || 0, usd: Number(r.usd) || 0 }))
    .sort((a, b) => a.usd - b.usd);
  const total = perRun.reduce((t, r) => t + r.usd, 0);
  const llm = perRun.reduce((t, r) => t + r.llm, 0);
  return {
    runs: rs.length,
    bugs: new Set(rs.map((r) => r.bug)).size,
    usd: dist(perRun.map((r) => r.usd)),
    total,
    llmShare: total ? llm / total : 0,
    perRun,
    toRca: dist(num(rs, "discovery_to_rca_s")),
    toEnd: dist(num(rs, "discovery_to_end_s")),
    pipeline: dist(num(rs, "pipeline_s")),
    turns: dist(num(rs, "turns")),
  };
}

export interface DecisionOps {
  report: string;
  rows: { decision: string; n: number; accuracy: number; coverage: number; accAtTau: number; p50: number; p95: number; usdPer1k: number }[];
}

/** Per-decision latency, cost and accuracy of the live Clef calls, from the latest report with decisions.csv. */
export function decisionOps(): DecisionOps | null {
  const dirs = fs
    .readdirSync(REPORTS)
    .filter((d) => fs.existsSync(path.join(REPORTS, d, "decisions.csv")))
    .sort();
  const report = dirs[dirs.length - 1];
  if (!report) return null;
  const rows = parseCsv(fs.readFileSync(path.join(REPORTS, report, "decisions.csv"), "utf8")).map((r) => ({
    decision: r.decision,
    n: Number(r.n),
    accuracy: Number(r.accuracy),
    coverage: Number(r.coverage_at_tau),
    accAtTau: Number(r.accuracy_at_tau),
    p50: Number(r.latency_p50_ms) / 1000,
    p95: Number(r.latency_p95_ms) / 1000,
    usdPer1k: Number(r.usd_per_1k),
  }));
  return { report, rows };
}

export interface Limits {
  agentTypes: number;
  nodes: { node: string; turns: string; tools: string; usd: string }[];
  subagents: { turns: string; tools: string; usd: string; wall: string; parallel: string };
}

/** The per-node caps every agent type sets, and the subagent defaults (configs/agent_types, configs/subagents.yaml). */
export function limits(): Limits {
  const dir = path.join(ROOT, "configs", "agent_types");
  const files = fs.readdirSync(dir).filter((f) => f.endsWith(".yaml"));
  const seen: Record<string, Record<string, Set<string>>> = {};
  for (const f of files) {
    const text = fs.readFileSync(path.join(dir, f), "utf8");
    const block = text.split(/^nodes:\s*$/m)[1]?.split(/^\S/m)[0] ?? "";
    for (const m of block.matchAll(/^ {2}(\w+):\s*\n((?: {4}.*\n?)*)/gm)) {
      const node = (seen[m[1]] ??= {});
      for (const k of ["max_turns", "max_tool_calls", "max_budget_usd"]) {
        const v = m[2].match(new RegExp(`^\\s+${k}:\\s*([\\d.]+)`, "m"))?.[1];
        if (v) (node[k] ??= new Set()).add(v);
      }
    }
  }
  const show = (s?: Set<string>) => (s ? [...s].sort((a, b) => Number(a) - Number(b)).join("–") : "—");
  const sub = fs.readFileSync(path.join(ROOT, "configs", "subagents.yaml"), "utf8");
  const field = (k: string) => sub.match(new RegExp(`^\\s*${k}:\\s*([\\d.]+)`, "m"))?.[1] ?? "—";
  return {
    agentTypes: files.length,
    nodes: Object.entries(seen).map(([node, v]) => ({
      node,
      turns: show(v.max_turns),
      tools: show(v.max_tool_calls),
      usd: show(v.max_budget_usd),
    })),
    subagents: { turns: field("max_turns"), tools: field("max_tool_calls"), usd: field("max_budget_usd"), wall: field("max_wall_s"), parallel: field("max_parallel") },
  };
}

export interface Claims {
  validatedButHiddenFails: number; // code-bug runs whose own test passed but the hidden one failed
  hiddenRan: number;
  claims: number;
  unsupported: number;
  models: string[];
  near: number; // root cause right or close
  n: number;
}

/** Honesty numbers from the headline runs. */
export function claims(data: Results): Claims {
  const rs = data.runs;
  const hid = rs.filter((r) => r.hidden_tests === "True" || r.hidden_tests === "False");
  const sum = (k: string) => rs.reduce((t, r) => t + (Number(r[k]) || 0), 0);
  return {
    validatedButHiddenFails: hid.filter((r) => r.validated === "True" && r.hidden_tests === "False").length,
    hiddenRan: hid.length,
    claims: sum("claims"),
    unsupported: sum("claims_unsupported"),
    models: [...new Set(rs.map((r) => r.model).filter(Boolean))],
    near: rs.filter((r) => r.rca === "exact" || r.rca === "directional").length,
    n: rs.length,
  };
}
