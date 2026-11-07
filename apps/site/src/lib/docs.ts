// Build-time readers for the repository's design material: the ADRs, the Clef decision templates, the MCP server
// table and the threat model. Like data.ts, nothing here is typed by hand — every page is rendered from the files.
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(process.cwd(), "..", "..");
const read = (p: string) => fs.readFileSync(path.join(ROOT, p), "utf8");

// ───────────────────────── ADRs ─────────────────────────

export interface Adr {
  slug: string; // 0001-fixed-plan
  n: string; // 0001
  title: string;
  status: string;
  date: string;
  /** the first sentence of its Decision section */
  gist: string;
  /** the body after the title and the status lines */
  body: string;
  file: string;
}

export function adrs(): Adr[] {
  const dir = "docs/adr";
  return fs
    .readdirSync(path.join(ROOT, dir))
    .filter((f) => /^\d{4}-.*\.md$/.test(f) && !f.startsWith("0000"))
    .sort()
    .map((f) => {
      const src = read(`${dir}/${f}`);
      const title = (src.match(/^#\s+\d{4}\.\s*(.*)$/m)?.[1] ?? f).trim();
      const meta = src.match(/^- Status:.*(?:\n- .*)*$/m)?.[0] ?? "";
      const status = meta.match(/Status:\s*([^·\n]+)/)?.[1].trim() ?? "";
      const date = meta.match(/Date:\s*([\d-]+)/)?.[1] ?? "";
      const body = src
        .replace(/^#\s+.*\n/, "")
        .replace(meta, "")
        .trim();
      const decision = body.split(/^## Decision\s*$/m)[1] ?? "";
      const first = decision
        .trim()
        .split("\n")
        .map((l) => l.replace(/^[-*]\s+/, "").trim())
        .join(" ")
        .replace(/[*`]/g, "");
      const gist = first.match(/^.*?[.:](?=\s|$)/)?.[0] ?? first.slice(0, 200);
      return { slug: f.replace(/\.md$/, ""), n: f.slice(0, 4), title, status, date, gist, body, file: `${dir}/${f}` };
    });
}

// ───────────────────────── Clef decision templates ─────────────────────────

type Y = string | number | boolean | null | Y[] | { [k: string]: Y };

/** Just enough YAML for the templates: nested maps, folded scalars (>-), flow lists and flow maps. */
function yaml(src: string): { [k: string]: Y } {
  const lines = src
    .split("\n")
    .map((l) => l.replace(/\s+#.*$/, "").replace(/^#.*$/, ""))
    .filter((l) => l.trim());
  let i = 0;
  const scalar = (s: string): Y => {
    s = s.trim();
    if (s.startsWith("[") || s.startsWith("{")) return flow(s);
    if (/^-?\d+(\.\d+)?$/.test(s)) return Number(s);
    if (s === "true" || s === "false") return s === "true";
    return s.replace(/^["']|["']$/g, "");
  };
  // split a flow collection's inside on top-level commas
  const split = (s: string) => {
    const out: string[] = [];
    let depth = 0;
    let q = "";
    let cur = "";
    for (const c of s) {
      if (q) {
        if (c === q) q = "";
      } else if (c === '"' || c === "'") q = c;
      else if (c === "[" || c === "{") depth++;
      else if (c === "]" || c === "}") depth--;
      else if (c === "," && depth === 0) {
        out.push(cur);
        cur = "";
        continue;
      }
      cur += c;
    }
    if (cur.trim()) out.push(cur);
    return out;
  };
  const flow = (s: string): Y => {
    const inner = s.slice(1, -1);
    if (s.startsWith("[")) return split(inner).map(scalar);
    const o: { [k: string]: Y } = {};
    for (const part of split(inner)) {
      const m = part.match(/^\s*("[^"]*"|'[^']*'|[^:]+):\s*(.*)$/);
      if (m) o[m[1].trim().replace(/^["']|["']$/g, "")] = scalar(m[2]);
    }
    return o;
  };
  const indent = (l: string) => l.length - l.trimStart().length;
  const block = (level: number): { [k: string]: Y } => {
    const o: { [k: string]: Y } = {};
    while (i < lines.length && indent(lines[i]) === level) {
      const m = lines[i].trim().match(/^([\w$*-]+):\s*(.*)$/);
      i++;
      if (!m) continue;
      const [, key, rest] = m;
      if (rest === ">-" || rest === ">" || rest === "|") {
        const parts: string[] = [];
        while (i < lines.length && indent(lines[i]) > level) parts.push(lines[i++].trim());
        o[key] = parts.join(rest === "|" ? "\n" : " ");
      } else if (rest === "") {
        o[key] = i < lines.length && indent(lines[i]) > level ? block(indent(lines[i])) : null;
      } else o[key] = scalar(rest);
    }
    return o;
  };
  return block(0);
}

export interface Question {
  name: string;
  type: string;
  instructions: string;
  /** choices or score levels; a `$name` string when filled in at run time */
  criteria: { k: string; d?: string }[] | string;
}
export interface Template {
  id: string; // D01
  name: string; // triage
  stage: string;
  description: string;
  model: string;
  questions: Question[];
  gate: string;
  perItem: boolean;
  tauHigh: number;
  tauLow: number;
  act: string | [string, string][];
  escalate: string;
  safeDefault: string;
  file: string;
}

const str = (y: Y | undefined) => (y === undefined || y === null ? "" : typeof y === "object" ? JSON.stringify(y) : String(y));

export function templates(): Template[] {
  const dir = "packages/decisions/templates";
  return fs
    .readdirSync(path.join(ROOT, dir))
    .filter((f) => /^D\d+_.*\.yaml$/.test(f))
    .sort()
    .map((f) => {
      const y = yaml(read(`${dir}/${f}`));
      const p = (y.policy ?? {}) as { [k: string]: Y };
      const qs = (y.questions ?? {}) as { [k: string]: Y };
      const act = p.act;
      return {
        id: f.slice(0, 3),
        name: f.slice(4).replace(/\.yaml$/, "").replace(/_/g, " "),
        stage: str(y.stage),
        description: str(y.description),
        model: str(y.model),
        questions: Object.entries(qs).map(([name, q]) => {
          const qq = (q ?? {}) as { [k: string]: Y };
          return {
            name,
            type: str(qq.type),
            instructions: str(qq.instructions),
            criteria: Array.isArray(qq.criteria)
              ? qq.criteria.map((c) => ({ k: str(c) }))
              : qq.criteria && typeof qq.criteria === "object"
                ? Object.entries(qq.criteria).map(([k, d]) => ({ k, d: str(d) }))
                : str(qq.criteria),
          };
        }),
        gate: str(p.question),
        perItem: p.per_item === true,
        tauHigh: Number(p.tau_high ?? 0),
        tauLow: Number(p.tau_low ?? 0),
        act: act && typeof act === "object" && !Array.isArray(act) ? Object.entries(act).map(([k, v]) => [k, str(v)] as [string, string]) : str(act),
        escalate: str(p.escalate),
        safeDefault: str(p.safe_default),
        file: `${dir}/${f}`,
      };
    });
}

// ───────────────────────── MCP servers ─────────────────────────

export interface McpServer {
  name: string;
  role: string; // "Sourcegraph's role"
  backedBy: string;
  tools: string[];
  writes: string;
}

/** The server table and the shared rules from docs/mcp.md. */
export function mcpServers(): { servers: McpServer[]; rules: string } {
  const src = read("docs/mcp.md");
  const servers = src
    .split("\n")
    .filter((l) => /^\| \*\*/.test(l))
    .map((l) => {
      const c = l
        .replace(/^\||\|$/g, "")
        .split("|")
        .map((s) => s.trim());
      const nm = c[0].match(/\*\*(.+?)\*\*\s*(?:\((.*)\))?/);
      return {
        name: nm?.[1] ?? c[0],
        role: nm?.[2] ?? "",
        backedBy: c[1],
        tools: [...c[2].matchAll(/`([^`]+)`/g)].map((m) => m[1]),
        writes: c[3] === "—" ? "" : c[3],
      };
    });
  const rules = src.match(/^Every server follows.*?\n\n((?:- .*\n(?: {2,}.*\n)*)+)/m)?.[1] ?? "";
  return { servers, rules };
}

// ───────────────────────── threat model ─────────────────────────

export function threatModel(): { intro: string; body: string; file: string } {
  const file = "docs/THREAT-MODEL.md";
  const src = read(file).replace(/^#\s+.*\n/, "");
  const at = src.search(/^## /m);
  return { intro: src.slice(0, at).trim(), body: src.slice(at), file };
}
