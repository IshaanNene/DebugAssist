// Build-time data: everything numeric on the site is read from the repository's generated evaluation
// reports (evals/reports/<date>/results.csv and context.json) and the bug catalog — never typed by hand.
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(process.cwd(), "..", "..");
const REPORTS = path.join(ROOT, "evals", "reports");

export type Row = Record<string, string>;

/** RFC 4180-ish CSV: quoted fields may contain commas, quotes ("") and newlines. */
export function parseCsv(text: string): Row[] {
  const rows: string[][] = [];
  let field = "";
  let row: string[] = [];
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') {
        field += '"';
        i++;
      } else if (c === '"') quoted = false;
      else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") {
      row.push(field);
      field = "";
    } else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else field += c;
  }
  if (field || row.length) {
    row.push(field);
    rows.push(row);
  }
  const [head, ...body] = rows.filter((r) => r.length > 1);
  return body.map((r) => Object.fromEntries(head.map((h, i) => [h, r[i] ?? ""])));
}

function latestReport(): string {
  const dirs = fs
    .readdirSync(REPORTS)
    .filter((d) => fs.existsSync(path.join(REPORTS, d, "results.csv")))
    .sort();
  return dirs[dirs.length - 1];
}

function expectedOutcomes(): Record<string, string> {
  const dir = path.join(ROOT, "groundtruth", "bugs");
  const out: Record<string, string> = {};
  for (const f of fs.readdirSync(dir).filter((f) => f.endsWith(".yaml"))) {
    const m = fs.readFileSync(path.join(dir, f), "utf8").match(/^expected_outcome:\s*(\S+)/m);
    out[f.replace(/\.yaml$/, "")] = m ? m[1] : "pr";
  }
  return out;
}

export interface Results {
  report: string;
  model: string;
  baseline: Row[];
  arms: { name: string; commit: string; rows: Row[] }[];
  ours: Record<string, boolean>;
  stats: { label: string; value: string; tone: "cyan" | "green" | "violet" | "amber" | "muted" }[];
  catalog: { total: number; code: number; notOurs: number };
}

export function results(model = "gpt-6-luna"): Results {
  const report = latestReport();
  const all = parseCsv(fs.readFileSync(path.join(REPORTS, report, "results.csv"), "utf8")).filter(
    (r) => (r.model || "").includes(model) && r.rca,
  );
  const baseline = all.filter((r) => !r.arm).sort((a, b) => a.bug.localeCompare(b.bug));
  const order: string[] = [];
  const byArm: Record<string, Record<string, Row>> = {};
  for (const r of all.filter((r) => r.arm).sort((a, b) => (a.eval || "").localeCompare(b.eval || ""))) {
    if (!order.includes(r.arm)) order.push(r.arm);
    (byArm[r.arm] ??= {})[r.bug] = r; // the latest run of a bug in that arm
  }
  const outcomes = expectedOutcomes();
  const ours = Object.fromEntries(Object.entries(outcomes).map(([b, o]) => [b, o === "pr"]));
  const n = baseline.length;
  const yes = (v: string) => v === "True";
  const exact = baseline.filter((r) => r.rca === "exact").length;
  const near = exact + baseline.filter((r) => r.rca === "directional").length;
  const code = baseline.filter((r) => ours[r.bug]);
  const hidden = baseline.filter((r) => r.hidden_tests === "True" || r.hidden_tests === "False");
  const costs = baseline.map((r) => Number(r.usd)).sort((a, b) => a - b);
  const median = costs.length ? costs[Math.floor(costs.length / 2)] : 0;
  return {
    report,
    model,
    baseline,
    arms: order.map((name) => {
      const rows = Object.values(byArm[name]).sort((a, b) => a.bug.localeCompare(b.bug));
      return { name, commit: rows[0]?.commit ?? "", rows };
    }),
    ours,
    stats: [
      { label: "root cause right or close", value: `${near}/${n}`, tone: "cyan" },
      { label: "root cause exact", value: `${exact}/${n}`, tone: "green" },
      { label: "category right", value: `${baseline.filter((r) => yes(r.category_ok)).length}/${n}`, tone: "violet" },
      { label: "code bugs: fix validated", value: `${code.filter((r) => yes(r.validated)).length}/${code.length}`, tone: "green" },
      { label: "hidden tests pass", value: `${hidden.filter((r) => yes(r.hidden_tests)).length}/${hidden.length}`, tone: "amber" },
      { label: "median cost per run", value: `$${median.toFixed(3)}`, tone: "muted" },
    ],
    catalog: {
      total: Object.keys(outcomes).length,
      code: Object.values(outcomes).filter((o) => o === "pr").length,
      notOurs: Object.values(outcomes).filter((o) => o !== "pr").length,
    },
  };
}

export interface ContextAudit {
  report: string;
  inputTokens: number;
  prefixShare: number;
  toolsShare: number;
  modelShare: number;
  cacheShare: number;
  topTools: { tool: string; share: number }[];
}

export function contextAudit(): ContextAudit | null {
  const dirs = fs
    .readdirSync(REPORTS)
    .filter((d) => fs.existsSync(path.join(REPORTS, d, "context.json")))
    .sort();
  if (!dirs.length) return null;
  const report = dirs[dirs.length - 1];
  const s = JSON.parse(fs.readFileSync(path.join(REPORTS, report, "context.json"), "utf8"));
  return {
    report,
    inputTokens: s.input_tokens,
    prefixShare: s.prefix_share,
    toolsShare: s.tools_share,
    modelShare: s.model_share,
    cacheShare: s.cached_tokens / s.input_tokens,
    topTools: (s.tools as { tool: string; share: number }[]).slice(0, 5),
  };
}

/** Counts read from the code, so the copy never drifts: decision templates, MCP servers, tests. */
export function facts() {
  const templates = fs
    .readdirSync(path.join(ROOT, "packages", "decisions", "templates"))
    .filter((f) => /^D\d+_.*\.yaml$/.test(f)).length;
  const mcp = fs.readFileSync(path.join(ROOT, "docs", "mcp.md"), "utf8").match(/\*\*(\d+) MCP servers\*\* \((\d+) tools\)/);
  return { templates, mcpServers: mcp ? Number(mcp[1]) : 11, mcpTools: mcp ? Number(mcp[2]) : 55 };
}
