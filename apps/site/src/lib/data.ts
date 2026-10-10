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

export type Lane = "rca" | "validated" | "hidden_tests";

/** One bug's results across the seeds of a sweep: how many runs passed each lane, out of how many applied. */
export interface BugAgg {
  bug: string;
  ours: boolean;
  runs: number;
  lanes: Record<Lane, { pass: number; n: number; exact?: number }>;
}

export interface Headline {
  label: string; // which sweep the grid shows
  eval: string; // its eval stamp (YYYYMMDD-HHMMSS)
  commit: string;
  seeds: number;
  current: boolean; // false: the original baseline, run before the later fixes
  bugs: BugAgg[];
}

export interface Results {
  report: string;
  model: string;
  baseline: Row[]; // the original full-catalog run (no arm): the "before" of every re-run panel
  headline: Headline;
  arms: { name: string; commit: string; rows: Row[] }[];
  ours: Record<string, boolean>;
  stats: { label: string; value: string; tone: "cyan" | "green" | "violet" | "amber" | "muted" }[];
  catalog: { total: number; code: number; notOurs: number };
}

const yes = (v: string) => v === "True";

function aggregate(rows: Row[], ours: Record<string, boolean>): BugAgg[] {
  const byBug: Record<string, Row[]> = {};
  for (const r of rows) (byBug[r.bug] ??= []).push(r);
  return Object.keys(byBug)
    .sort()
    .map((bug) => {
      const rs = byBug[bug];
      const ownCode = !!ours[bug];
      const hid = rs.filter((r) => r.hidden_tests === "True" || r.hidden_tests === "False");
      return {
        bug,
        ours: ownCode,
        runs: rs.length,
        lanes: {
          rca: {
            pass: rs.filter((r) => r.rca === "exact" || r.rca === "directional").length,
            exact: rs.filter((r) => r.rca === "exact").length,
            n: rs.length,
          },
          validated: ownCode ? { pass: rs.filter((r) => yes(r.validated)).length, n: rs.length } : { pass: 0, n: 0 },
          hidden_tests: { pass: hid.filter((r) => yes(r.hidden_tests)).length, n: hid.length },
        },
      };
    });
}

const stamp = (e: string) => (e ? `${e.slice(0, 4)}-${e.slice(4, 6)}-${e.slice(6, 8)}` : "");

export function results(model = "gpt-6-luna"): Results {
  const report = latestReport();
  const all = parseCsv(fs.readFileSync(path.join(REPORTS, report, "results.csv"), "utf8")).filter(
    (r) => (r.model || "").includes(model) && r.rca,
  );
  const outcomes = expectedOutcomes();
  const ours = Object.fromEntries(Object.entries(outcomes).map(([b, o]) => [b, o === "pr"]));
  const total = Object.keys(outcomes).length;
  const baseline = all.filter((r) => !r.arm).sort((a, b) => a.bug.localeCompare(b.bug));

  // Arms in run order; an arm that covers the whole catalog is a full re-run and becomes the headline.
  const order: string[] = [];
  const armRows: Record<string, Row[]> = {};
  for (const r of all.filter((r) => r.arm).sort((a, b) => (a.eval || "").localeCompare(b.eval || ""))) {
    if (!order.includes(r.arm)) order.push(r.arm);
    (armRows[r.arm] ??= []).push(r);
  }
  const full = order.filter((a) => new Set(armRows[a].map((r) => r.bug)).size >= total);
  const headArm = full[full.length - 1];
  const headRows = headArm ? armRows[headArm] : baseline;
  const headEval = headRows.map((r) => r.eval || "").sort().pop() ?? "";
  const headline: Headline = {
    label: headArm ?? "baseline",
    eval: headEval,
    commit: headRows[0]?.commit ?? "",
    seeds: Math.max(1, ...Object.values(aggregate(headRows, ours)).map((b) => b.runs)),
    current: !!headArm,
    bugs: aggregate(headRows, ours),
  };

  const runs = headRows;
  const n = runs.length;
  const exact = runs.filter((r) => r.rca === "exact").length;
  const near = exact + runs.filter((r) => r.rca === "directional").length;
  const code = runs.filter((r) => ours[r.bug]);
  const hidden = runs.filter((r) => r.hidden_tests === "True" || r.hidden_tests === "False");
  const costs = runs.map((r) => Number(r.usd)).sort((a, b) => a - b);
  const median = costs.length ? costs[Math.floor(costs.length / 2)] : 0;
  const frac = (a: number, b: number) => (headline.seeds > 1 ? `${Math.round((100 * a) / (b || 1))}%` : `${a}/${b}`);
  return {
    report,
    model,
    baseline,
    headline,
    arms: order
      .filter((a) => a !== headArm)
      .map((name) => {
        const latest: Record<string, Row> = {};
        for (const r of armRows[name]) latest[r.bug] = r; // the latest run of a bug in that arm
        const rows = Object.values(latest).sort((a, b) => a.bug.localeCompare(b.bug));
        return { name, commit: rows[0]?.commit ?? "", rows };
      }),
    ours,
    stats: [
      { label: "root cause right or close", value: frac(near, n), tone: "cyan" },
      { label: "root cause exact", value: frac(exact, n), tone: "green" },
      { label: "category right", value: frac(runs.filter((r) => yes(r.category_ok)).length, n), tone: "violet" },
      { label: "code bugs: fix validated", value: frac(code.filter((r) => yes(r.validated)).length, code.length), tone: "green" },
      { label: "hidden tests pass", value: frac(hidden.filter((r) => yes(r.hidden_tests)).length, hidden.length), tone: "amber" },
      { label: "median cost per run", value: `$${median.toFixed(3)}`, tone: "muted" },
    ],
    catalog: {
      total,
      code: Object.values(outcomes).filter((o) => o === "pr").length,
      notOurs: Object.values(outcomes).filter((o) => o !== "pr").length,
    },
  };
}

export { stamp as evalDate };

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

export interface FeaturedRun {
  runId: string;
  bug: string;
  issue: string;
  agentType: string;
  location: string;
  claims: number;
  unsupported: number;
  tier: string;
  hiddenTest: string;
  turns: number;
  usd: number;
  wallS: number;
  decisions: number;
}

/** One real baseline run, replayed in the hero: exact root cause, validated fix, hidden test passing. */
export function featuredRun(data: Results): FeaturedRun | null {
  const good = data.baseline.filter(
    (r) => r.rca === "exact" && r.validated === "True" && r.hidden_tests === "True" && r.claims_unsupported === "0",
  );
  const r = good.find((x) => x.agent_type === "web-crash") ?? good[0];
  if (!r) return null;
  let hiddenTest = "";
  try {
    hiddenTest = (JSON.parse(r.hidden_detail) as { test: string }[])[0]?.test ?? "";
  } catch {
    hiddenTest = "";
  }
  return {
    runId: r.run_id,
    bug: r.bug,
    issue: r.issue,
    agentType: r.agent_type,
    location: r.rca_location,
    claims: Number(r.claims),
    unsupported: Number(r.claims_unsupported),
    tier: r.tier,
    hiddenTest,
    turns: Number(r.turns),
    usd: Number(r.usd),
    wallS: Number(r.wall_s),
    decisions: Number(r.labelled_decisions),
  };
}

export interface ContextArm {
  arm: string;
  runs: number;
  perRun: number;
  perTurn: number;
  cacheRate: number;
  readFileShare: number;
  toolsShare: number;
}

/** Per-arm context audits (`debugassist eval context --name <arm>`) saved next to the latest report. */
export function contextArms(): ContextArm[] {
  const dir = path.join(REPORTS, latestReport());
  return fs
    .readdirSync(dir)
    .filter((f) => /^context-.+\.json$/.test(f))
    .sort()
    .map((f) => {
      const s = JSON.parse(fs.readFileSync(path.join(dir, f), "utf8"));
      const runs = Number(s.runs) || 0;
      const read = (s.tools as { tool: string; share: number }[]).find((t) => t.tool === "read_file");
      const turns = (s.nodes as { agents: number; turns_avg: number }[]).reduce((n, x) => n + x.agents * x.turns_avg, 0);
      return {
        arm: f.replace(/^context-/, "").replace(/\.json$/, ""),
        runs,
        perRun: runs ? s.input_tokens / runs : 0,
        perTurn: turns ? s.input_tokens / turns : 0,
        cacheRate: s.input_tokens ? s.cached_tokens / s.input_tokens : 0,
        readFileShare: read ? read.share : 0,
        toolsShare: s.tools_share,
      };
    });
}
