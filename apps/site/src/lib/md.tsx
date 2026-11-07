// A small Markdown renderer for the repository's own docs (ADRs, the threat model, the MCP notes), so their
// pages are built from the files themselves and can never drift. It covers what those files use: headings,
// paragraphs, lists, tables, block quotes, fenced code, and inline code, bold, italics and links.
import Link from "next/link";
import path from "node:path";
import type { ReactNode } from "react";
import { doc } from "@/components/ui";

/** Where a link in a doc goes: ADRs and the threat model have pages here; everything else is on GitHub. */
export function resolveHref(href: string, from: string): { href: string; internal: boolean } {
  if (/^[a-z]+:/.test(href) || href.startsWith("#")) return { href, internal: false };
  const [p, hash] = href.split("#");
  const target = path.posix.normalize(path.posix.join(path.posix.dirname(from), p));
  const adr = target.match(/^docs\/adr\/(\d{4}-[\w-]+)\.md$/);
  if (adr) return { href: `/design/${adr[1]}/`, internal: true };
  if (target === "docs/THREAT-MODEL.md") return { href: "/safety/#threat-model", internal: true };
  if (target === "docs/mcp.md") return { href: "/system/#servers", internal: true };
  if (target === "docs/github-app.md") return { href: `/repo/${hash ? `#${hash}` : ""}`, internal: true };
  if (target === "docs/LESSONS.md") return { href: "/lessons/", internal: true };
  return { href: doc(target) + (hash ? `#${hash}` : ""), internal: false };
}

const A = ({ href, from, children }: { href: string; from: string; children: ReactNode }) => {
  const r = resolveHref(href, from);
  const cls = "text-t1 underline decoration-line-2 underline-offset-[3px] transition-colors hover:decoration-t1";
  return r.internal ? (
    <Link className={cls} href={r.href}>
      {children}
    </Link>
  ) : (
    <a className={cls} href={r.href}>
      {children}
    </a>
  );
};

/** Inline Markdown: `code`, **bold**, *italic*, [text](href). */
export function inline(text: string, from: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /`([^`]+)`|\*\*(.+?)\*\*|\*([^*\s][^*]*?)\*|\[([^\]]+)\]\(([^)\s]+)\)/g;
  let last = 0;
  let k = 0;
  for (let m = re.exec(text); m; m = re.exec(text)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    if (m[1] !== undefined)
      out.push(
        <code key={k++} className="border border-line bg-sunk/70 px-1 py-px font-mono text-[0.86em] text-t1">
          {m[1]}
        </code>,
      );
    else if (m[2] !== undefined) out.push(<strong key={k++} className="font-semibold text-t1">{inline(m[2], from)}</strong>);
    else if (m[3] !== undefined) out.push(<em key={k++}>{inline(m[3], from)}</em>);
    else
      out.push(
        <A key={k++} href={m[5]} from={from}>
          {inline(m[4], from)}
        </A>,
      );
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const slug = (s: string) =>
  s
    .toLowerCase()
    .replace(/[`*]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

export type Block =
  | { t: "h"; level: number; text: string }
  | { t: "p"; text: string }
  | { t: "ul" | "ol"; items: string[] }
  | { t: "table"; head: string[]; rows: string[][] }
  | { t: "quote"; text: string }
  | { t: "code"; lang: string; text: string };

const cells = (line: string) =>
  line
    .trim()
    .replace(/^\||\|$/g, "")
    .split(/(?<!\\)\|/)
    .map((c) => c.trim());

export function parse(src: string): Block[] {
  const lines = src.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    const fence = line.match(/^```(\w*)/);
    if (fence) {
      const body: string[] = [];
      for (i++; i < lines.length && !lines[i].startsWith("```"); i++) body.push(lines[i]);
      blocks.push({ t: "code", lang: fence[1], text: body.join("\n") });
      i++;
      continue;
    }
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) {
      blocks.push({ t: "h", level: h[1].length, text: h[2] });
      i++;
      continue;
    }
    if (line.trimStart().startsWith("|")) {
      const rows: string[][] = [];
      for (; i < lines.length && lines[i].trimStart().startsWith("|"); i++) rows.push(cells(lines[i]));
      const body = rows.filter((r) => !r.every((c) => /^:?-{2,}:?$/.test(c)));
      blocks.push({ t: "table", head: body[0] ?? [], rows: body.slice(1) });
      continue;
    }
    if (line.startsWith(">")) {
      const body: string[] = [];
      for (; i < lines.length && lines[i].startsWith(">"); i++) body.push(lines[i].replace(/^>\s?/, ""));
      blocks.push({ t: "quote", text: body.join(" ") });
      continue;
    }
    const li = line.match(/^(\s*)([-*]|\d+\.)\s+(.*)$/);
    if (li) {
      const ordered = /\d/.test(li[2]);
      const items: string[] = [];
      while (i < lines.length) {
        const m = lines[i].match(/^(\s*)([-*]|\d+\.)\s+(.*)$/);
        if (m) {
          items.push(m[3]);
          i++;
        } else if (lines[i].trim() && /^\s+/.test(lines[i]) && items.length) {
          items[items.length - 1] += " " + lines[i].trim();
          i++;
        } else break;
      }
      blocks.push({ t: ordered ? "ol" : "ul", items });
      continue;
    }
    const body: string[] = [];
    for (; i < lines.length && lines[i].trim() && !/^(#{1,4}\s|```|\||>|\s*([-*]|\d+\.)\s)/.test(lines[i]); i++)
      body.push(lines[i].trim());
    blocks.push({ t: "p", text: body.join(" ") });
  }
  return blocks;
}

/** The headings of a doc, for an "on this page" list. */
export function outline(src: string, level = 2) {
  return parse(src)
    .filter((b): b is Extract<Block, { t: "h" }> => b.t === "h" && b.level === level)
    .map((b) => ({ id: slug(b.text), text: b.text.replace(/[`*]/g, "") }));
}

/** Render a doc (or part of one). `from` is its repository path, for resolving relative links. */
export function Markdown({ src, from, skipTitle = true }: { src: string; from: string; skipTitle?: boolean }) {
  const blocks = parse(src).filter((b, i) => !(skipTitle && i === 0 && b.t === "h" && b.level === 1));
  return (
    <div className="prose-da">
      {blocks.map((b, k) => {
        switch (b.t) {
          case "h": {
            const id = slug(b.text);
            if (b.level <= 2)
              return (
                <h2 key={k} id={id} className="scroll-mt-24">
                  {inline(b.text, from)}
                </h2>
              );
            return (
              <h3 key={k} id={id} className="scroll-mt-24">
                {inline(b.text, from)}
              </h3>
            );
          }
          case "p":
            return <p key={k}>{inline(b.text, from)}</p>;
          case "ul":
          case "ol": {
            const L = b.t;
            return (
              <L key={k}>
                {b.items.map((it, j) => (
                  <li key={j}>{inline(it, from)}</li>
                ))}
              </L>
            );
          }
          case "quote":
            return <blockquote key={k}>{inline(b.text, from)}</blockquote>;
          case "code":
            return (
              <pre key={k}>
                <code>{b.text}</code>
              </pre>
            );
          case "table":
            return (
              <div key={k} className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      {b.head.map((c, j) => (
                        <th key={j}>{inline(c, from)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {b.rows.map((r, j) => (
                      <tr key={j}>
                        {r.map((c, n) => (
                          <td key={n}>{inline(c, from)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
        }
      })}
    </div>
  );
}
