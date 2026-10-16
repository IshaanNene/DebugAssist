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
  /** Later arms that re-ran some bugs with as many seeds: those bugs show their latest run. */
  updated: { arm: string; commit: string; bugs: string[] }[];
}

/** A re-run panel: the same bugs before (the previous whole-catalog run) and after (this arm). */
export interface ArmPanel {
  name: string;
  commit: string;
  beforeLabel: string;
  bugs: { bug: string; before: BugAgg["lanes"]; after: BugAgg["lanes"] }[];
  near: [number, number]; // runs with the root cause right or close, before → after (as rates when seeded)
  passed: [number, number]; // hidden tests passing
  seeded: boolean;
}

export interface Results {
  report: string;
  model: string;
  baseline: Row[]; // the original full-catalog run (no arm)
  headline: Headline;
  arms: ArmPanel[];
  ablation: Ablation | null;
  ours: Record<string, boolean>;
  stats: { label: string; value: string; tone: "cyan" | "green" | "violet" | "amber" | "muted" }[];
  catalog: { total: number; code: number; notOurs: number };
}

const yes = (v: string) => v === "True";

/** The decider ablation: the same pipeline with an LLM making every Clef decision, on the bugs it ran, against each
 *  bug's latest Clef run. Rates are the mean of per-bug pass rates, so a bug counts once however many seeds it had;
 *  a code bug with no fix attempted counts as not validated and its hidden test as not passing. */
export interface Ablation {
  arm: string;
  commit: string;
  bugs: number;
  clefSeeds: number;
  clefCommits: string[]; // the code the Clef runs it is compared with ran on
  lanes: { label: string; clef: number; noClef: number }[];
}

function ablation(arm: string | undefined, armRows: Record<string, Row[]>, latest: Record<string, Row[]>, ours: Record<string, boolean>): Ablation | null {
  if (!arm) return null;
  const nc = armRows[arm].filter((r) => r.rca);
  const bugs = [...new Set(nc.map((r) => r.bug))].filter((b) => latest[b]?.length);
  if (!bugs.length) return null;
  const rate = (rs: Row[], f: (r: Row) => boolean) => rs.filter(f).length / rs.length;
  const lanes: [string, (r: Row) => boolean, boolean][] = [
    ["root cause right or close", (r) => r.rca === "exact" || r.rca === "directional", false],
    ["root cause exact", (r) => r.rca === "exact", false],
    ["code bugs: fix validated", (r) => yes(r.validated), true],
    ["code bugs: hidden test passes", (r) => yes(r.hidden_tests), true],
  ];
  const commit = nc[0]?.commit ?? "";
  return {
    arm,
    commit,
    bugs: bugs.length,
    clefSeeds: Math.max(...bugs.map((b) => latest[b].length)),
    clefCommits: [...new Set(bugs.flatMap((b) => latest[b].map((r) => r.commit.replace(/-dirty$/, ""))))].sort(), // -dirty: harness-only edits
    lanes: lanes.map(([label, f, codeOnly]) => {
      const set = codeOnly ? bugs.filter((b) => ours[b]) : bugs;
      const mean = (pick: (b: string) => Row[]) => set.reduce((n, b) => n + rate(pick(b), f), 0) / (set.length || 1);
      return { label, clef: mean((b) => latest[b]), noClef: mean((b) => nc.filter((r) => r.bug === b)) };
    }),
  };
}
const EMPTY: BugAgg["lanes"] = { rca: { pass: 0, n: 0 }, validated: { pass: 0, n: 0 }, hidden_tests: { pass: 0, n: 0 } };

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
  // Catalog bugs only: real open-source bugs (REAL-*) are reported on their own (realBugs).
  const all = parseCsv(fs.readFileSync(path.join(REPORTS, report, "results.csv"), "utf8")).filter(
    (r) => (r.model || "").includes(model) && r.rca && !r.bug.startsWith("REAL-"),
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
  const baseRows = headArm ? armRows[headArm] : baseline;
  const seedsOf = (rs: Row[], bug: string) => rs.filter((r) => r.bug === bug).length;
  const headSeeds = Math.max(1, ...aggregate(baseRows, ours).map((b) => b.runs));

  // A later arm that re-ran a bug with as many seeds replaces that bug's cells: the grid shows each bug's latest
  // full-strength run, and says which code each part ran on. One-seed spot checks never replace three seeds.
  // Context-engineering arms measure tokens, decider arms (no-clef-*) are ablations and real-* arms run real
  // open-source bugs (shown on their own), fixwidth-*, repro2-* and callers-* are fix-width experiments: none is a re-run of
  // the catalog's fixes.
  const isRerun = (a: string) => !["context-", "no-clef", "real-", "fixwidth-", "repro2-", "callers-"].some((p) => a.startsWith(p));
  const later = headArm ? order.slice(order.indexOf(headArm) + 1).filter(isRerun) : [];
  const latest: Record<string, Row[]> = {};
  for (const r of baseRows) (latest[r.bug] ??= []).push(r);
  const updated: Headline["updated"] = [];
  for (const a of later) {
    const bugs = [...new Set(armRows[a].map((r) => r.bug))].filter((b) => seedsOf(armRows[a], b) >= headSeeds).sort();
    if (!bugs.length) continue;
    for (const b of bugs) latest[b] = armRows[a].filter((r) => r.bug === b);
    updated.push({ arm: a, commit: armRows[a][0]?.commit ?? "", bugs });
  }
  const headRows = Object.values(latest).flat();
  const headEval = headRows.map((r) => r.eval || "").sort().pop() ?? "";
  const headline: Headline = {
    label: headArm ?? "baseline",
    eval: headEval,
    commit: baseRows[0]?.commit ?? "",
    seeds: headSeeds,
    current: !!headArm,
    bugs: aggregate(headRows, ours),
    updated,
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

  // Re-run panels: arms before the headline compare with the first run; arms after it with the headline run.
  const nearOf = (rs: Row[]) => rs.filter((r) => r.rca === "exact" || r.rca === "directional").length;
  const passOf = (rs: Row[]) => rs.filter((r) => r.hidden_tests === "True").length;
  const hid = (rs: Row[]) => rs.filter((r) => r.hidden_tests === "True" || r.hidden_tests === "False");
  const panel = (name: string): ArmPanel => {
    const isLater = later.includes(name);
    // after the headline, only bugs re-run with as many seeds are compared (one-seed spot checks are in the report)
    const after = isLater ? armRows[name].filter((r) => seedsOf(armRows[name], r.bug) >= headSeeds) : armRows[name];
    const before = isLater ? baseRows : baseline;
    const bugs = [...new Set(after.map((r) => r.bug))].sort();
    const pick = (rs: Row[]) => rs.filter((r) => bugs.includes(r.bug));
    const b = pick(before);
    const seeded = isLater && headSeeds > 1;
    const rate = (k: number, of: number) => (seeded ? Math.round((100 * k) / (of || 1)) : k);
    return {
      name,
      commit: after[0]?.commit ?? "",
      beforeLabel: isLater ? `${headArm} (${baseRows[0]?.commit ?? ""})` : "the first run (7 Oct)",
      bugs: bugs.map((bug) => ({
        bug,
        before: aggregate(before.filter((r) => r.bug === bug), ours)[0]?.lanes ?? EMPTY,
        after: aggregate(after.filter((r) => r.bug === bug), ours)[0].lanes,
      })),
      near: [rate(nearOf(b), b.length), rate(nearOf(after), after.length)],
      passed: [rate(passOf(b), hid(b).length), rate(passOf(after), hid(after).length)],
      seeded,
    };
  };
  return {
    report,
    model,
    baseline,
    headline,
    arms: order.filter((a) => a !== headArm && isRerun(a)).map(panel),
    ablation: ablation(order.filter((a) => a.startsWith("no-clef")).pop(), armRows, latest, ours),
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

export interface DeciderRow {
  decision: string;
  n: number;
  acc: Record<"clef" | "clef-flash" | "llm" | "rules", number | null>;
}

/** The decision replay (E1): each logged decision re-decided by Clef, Clef-flash, an LLM and rules, scored against
 *  the catalog. Read from the latest report's e1.csv. */
export function deciderReplay(): DeciderRow[] {
  const file = path.join(REPORTS, latestReport(), "e1.csv");
  if (!fs.existsSync(file)) return [];
  const rows = parseCsv(fs.readFileSync(file, "utf8"));
  const by: Record<string, DeciderRow> = {};
  for (const r of rows) {
    const d = (by[r.decision] ??= { decision: r.decision, n: 0, acc: { clef: null, "clef-flash": null, llm: null, rules: null } });
    const b = r.backend as keyof DeciderRow["acc"];
    if (b in d.acc) d.acc[b] = r.accuracy === "" ? null : Number(r.accuracy);
    if (b === "clef") d.n = Number(r.n);
  }
  // a rules baseline of 0 means "no rule for this decision", not a score
  return Object.values(by).map((d) => ({ ...d, acc: { ...d.acc, rules: d.acc.rules ? d.acc.rules : null } }));
}

export interface RealBug {
  id: string;
  title: string;
  issue: string; // upstream issue URL
  fixPr: string; // upstream fix PR URL
  arm: string;
  decider: string; // which decider the runs used
  runs: number;
  rcaExact: number;
  rcaNear: number;
  validated: number;
  hidden: number;
  hiddenRan: number;
  medianUsd: number;
}

/** Real open-source bugs (groundtruth/real/REAL-*): each case's latest arm, from the latest report. */
export function realBugs(): RealBug[] {
  const dir = path.join(ROOT, "groundtruth", "real");
  if (!fs.existsSync(dir)) return [];
  const rows = parseCsv(fs.readFileSync(path.join(REPORTS, latestReport(), "results.csv"), "utf8")).filter(
    (r) => r.bug?.startsWith("REAL-") && r.rca,
  );
  return fs
    .readdirSync(dir)
    .filter((f) => /^REAL-\d+\.yaml$/.test(f))
    .sort()
    .flatMap((f) => {
      const id = f.replace(/\.yaml$/, "");
      const text = fs.readFileSync(path.join(dir, f), "utf8");
      // one scalar from the YAML: comments need a space before #; quoted values are unquoted ('' → ')
      const field = (k: string) => {
        const v = text.match(new RegExp(`^\\s*${k}:\\s*(.+?)(\\s+#.*)?$`, "m"))?.[1] ?? "";
        const q = v.match(/^(['"])(.*)\1$/);
        return q ? (q[1] === "'" ? q[2].replaceAll("''", "'") : q[2]) : v;
      };
      const mine = rows.filter((r) => r.bug === id && (r.arm ?? "").startsWith("real-"));
      if (!mine.length) return [];
      const arm = mine.map((r) => r.arm).sort().pop() ?? "";
      const rs = mine.filter((r) => r.arm === arm);
      const costs = rs.map((r) => Number(r.usd)).sort((a, b) => a - b);
      // every real case is a code bug: a run that made no fix counts as not passing (the denominator is every run)
      const ran = rs;
      return [
        {
          id,
          title: field("title"),
          issue: field("issue"),
          fixPr: field("fix_pr"),
          arm,
          decider: (rs[0]?.config ?? "").startsWith("no-clef") ? "LLM decider" : "Clef",
          runs: rs.length,
          rcaExact: rs.filter((r) => r.rca === "exact").length,
          rcaNear: rs.filter((r) => r.rca === "exact" || r.rca === "directional").length,
          validated: rs.filter((r) => r.validated === "True").length,
          hidden: ran.filter((r) => r.hidden_tests === "True").length,
          hiddenRan: ran.length,
          medianUsd: costs.length ? costs[Math.floor(costs.length / 2)] : 0,
        },
      ];
    });
}

interface Tally {
  pass: number;
  ran: number;
}

export interface FixWidth {
  arm: string;
  /** upstream's test on the real bugs, over runs that made a fix: the real-* arms, then the experiment */
  before: Tally;
  after: Tally;
  /** REAL-001, the case the rules were written for */
  target: { before: Tally; after: Tally };
  /** the second-reproduction arms (repro2-*: the report alone; callers-*: also the code's other uses), as run:
   * per bug, the hidden test, the second test's verdict on the shipped fix, and the fixes it sent back */
  checks: { arm: string; bugs: { bug: string; hidden: Tally; second: Tally; rejected: number }[] }[];
}

/** The fix-width experiments: prompt rules (fixwidth-*, reverted) and a second reproduction (repro2-*, callers-*,
 * off by default), against the real bugs' own arms. */
export function fixWidth(): FixWidth | null {
  const all = parseCsv(fs.readFileSync(path.join(REPORTS, latestReport(), "results.csv"), "utf8"));
  const fixed = (r: Row) => r.hidden_tests === "True" || r.hidden_tests === "False";
  const rows = all.filter((r) => r.bug?.startsWith("REAL-") && fixed(r));
  const latestArm = (p: string) =>
    all
      .map((r) => r.arm ?? "")
      .filter((a) => a.startsWith(p))
      .sort()
      .pop();
  const arm = latestArm("fixwidth-");
  if (!arm) return null;
  const count = (rs: Row[]): Tally => ({ pass: rs.filter((r) => r.hidden_tests === "True").length, ran: rs.length });
  const before = rows.filter((r) => (r.arm ?? "").startsWith("real-"));
  const after = rows.filter((r) => r.arm === arm);
  const verdicts = (r: Row): string[] => {
    try {
      return JSON.parse(r.repro2 || "[]") as string[];
    } catch {
      return [];
    }
  };
  const check = (a: string) => {
    const rs = all.filter((r) => r.arm === a && fixed(r));
    return {
      arm: a,
      bugs: [...new Set(rs.map((r) => r.bug))].sort().map((bug) => {
        const mine = rs.filter((r) => r.bug === bug);
        // the second test's verdict on the fix that shipped is the last attempt it checked
        const last = mine.map((r) => verdicts(r).at(-1) ?? "unchecked").filter((v) => v !== "unchecked");
        return {
          bug,
          hidden: count(mine),
          second: { pass: last.filter((v) => v === "pass").length, ran: last.length },
          rejected: mine.reduce((n, r) => n + verdicts(r).filter((v) => v === "fail").length, 0),
        };
      }),
    };
  };
  return {
    arm,
    before: count(before),
    after: count(after),
    target: {
      before: count(before.filter((r) => r.bug === "REAL-001")),
      after: count(after.filter((r) => r.bug === "REAL-001")),
    },
    checks: ["repro2-", "callers-"].flatMap((p) => {
      const a = latestArm(p);
      return a ? [check(a)] : [];
    }),
  };
}
