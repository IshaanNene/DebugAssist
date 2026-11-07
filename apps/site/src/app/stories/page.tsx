import type { Metadata } from "next";
import Link from "next/link";
import { Escapes, WhereNumbersBroke } from "@/components/figs";
import { ChapterPage, Figure, Section } from "@/components/Page";
import { lessons, planAmendments, type Lesson } from "@/lib/docs";
import { inline } from "@/lib/md";

export const metadata: Metadata = {
  title: "Field notes — DebugAssist",
  description: "The problems that cost real time building DebugAssist, as case files: what happened, why, what fixed it and what stops it coming back.",
};

const SRC = "docs/LESSONS.md";

// Case files, grouped by what they teach. Each entry is picked by its title from docs/LESSONS.md and rendered from
// it; the group intros are ours.
const THEMES: { id: string; title: string; intro: string; picks: string[] }[] = [
  {
    id: "numbers",
    title: "When the numbers lied",
    intro:
      "The most expensive bugs were in the measurement, not the agent. Each was caught by reading a result that looked too good, or two numbers that should have agreed and didn't.",
    picks: ["A scorer bug inflated the headline", "The headline showed old code", "Rates over mismatched runs", "A scratch script is not a source", "The central claim was never tested"],
  },
  {
    id: "system",
    title: "When the model was right and the system wasn't",
    intro: "Several failures blamed on the model were the harness: a shell, a tool, a routing rule that threw away a correct answer.",
    picks: ["The right answer can still score as a miss", "Every Go sandbox command failed", "No Python test ever ran in the sandbox", "The edit tool ate the agents"],
  },
  {
    id: "no-model",
    title: "When a model was the wrong tool",
    intro:
      "Fixes kept passing the agent's own test and failing the hidden one. Three model-based checkers agreed with the narrow fixes; a few hundred lines of plain Python did not.",
    picks: ["A second reader of the same report", "Giving the checker more of the repo", "The check that worked needed no model", "Replay a new check on old runs"],
  },
  {
    id: "real",
    title: "Real bugs bite back",
    intro: "Moving from the catalog to public open-source issues found assumptions the catalog could not.",
    picks: ["A real issue can carry its own answer", "An agent's reproduction tests the fix", "The pipeline assumed one stack"],
  },
  {
    id: "machine",
    title: "Providers and the machine",
    intro: "Timeouts that never fired, a routing funnel down to one overloaded host, and a laptop whose cloud sync quietly took files away.",
    picks: ["Calls hung for minutes", "Every eval call hit 429", "iCloud evicted the repo", "iCloud evicted the git objects"],
  },
];

function Case({ c, n }: { c: Lesson; n: number }) {
  return (
    <article className="fx border border-line bg-surface">
      <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-5 py-2.5 font-mono text-[11px] text-t3">
        <span>
          <span className="text-t1">Case {String(n).padStart(2, "0")}</span> · {c.section.replace(/^\d+\.\s*/, "")}
        </span>
      </header>
      <div className="p-5 sm:p-6">
        <h3 className="max-w-[40ch] text-[20px] font-medium leading-[1.3] tracking-[-0.015em] text-t1">{inline(c.title.replace(/\.$/, ""), SRC)}</h3>
        <dl className="mt-5 grid gap-4 text-[14.5px] leading-[1.65]">
          {c.what && (
            <div className="grid gap-1 sm:grid-cols-[110px_minmax(0,1fr)] sm:gap-5">
              <dt className="font-mono text-[11px] uppercase tracking-[0.08em] text-t4 sm:pt-1">What happened</dt>
              <dd className="text-t2">{inline(c.what, SRC)}</dd>
            </div>
          )}
          {c.fix && (
            <div className="grid gap-1 sm:grid-cols-[110px_minmax(0,1fr)] sm:gap-5">
              <dt className="font-mono text-[11px] uppercase tracking-[0.08em] text-t4 sm:pt-1">The fix</dt>
              <dd className="text-t1">{inline(c.fix, SRC)}</dd>
            </div>
          )}
          {c.guards.map((g) => {
            const [k, ...rest] = g.split(":");
            return (
              <div key={g} className="grid gap-1 border-t border-line pt-4 sm:grid-cols-[110px_minmax(0,1fr)] sm:gap-5">
                <dt className="font-mono text-[11px] uppercase tracking-[0.08em] text-t1 sm:pt-1">{k}</dt>
                <dd className="caveat text-[16px] text-t2">{inline(rest.join(":").trim(), SRC)}</dd>
              </div>
            );
          })}
        </dl>
      </div>
    </article>
  );
}

export default function StoriesPage() {
  const all = lessons();
  const find = (p: string) => all.find((l) => l.title.startsWith(p));
  const amendments = planAmendments();
  let n = 0;
  const themes = THEMES.map((t) => ({ ...t, cases: t.picks.map(find).filter((c): c is Lesson => !!c) }));
  const shown = themes.reduce((a, t) => a + t.cases.length, 0);
  // case numbers in page order, so the figure can point at them
  const caseNo: Record<string, string> = {};
  themes.flatMap((t) => t.cases).forEach((c, i) => (caseNo[c.title] = String(i + 1).padStart(2, "0")));
  // where in the measurement chain each "numbers lied" case broke
  const STAGE: Record<string, string> = {
    "The central claim was never tested": "thesis",
    "A scorer bug inflated the headline": "score",
    "A scratch script is not a source": "report",
    "The headline showed old code": "site",
    "Rates over mismatched runs": "site",
  };
  const marks: Record<string, string[]> = {};
  for (const [prefix, stage] of Object.entries(STAGE)) {
    const c = find(prefix);
    if (c) (marks[stage] ??= []).push(`Case ${caseNo[c.title]}`);
  }

  return (
    <ChapterPage
      chapter="/stories/"
      title={
        <>
          The problems that <span className="hl">cost real time.</span>
        </>
      }
      lead={
        <>
          Building an agent that debugs production is mostly debugging the agent, its harness and its measurements. These
          are the case files worth reading — {shown} of the {all.length} in the lessons log, each with what happened, the
          fix, and what now stops it coming back.
        </>
      }
      sources={[SRC, "docs/adr/0009-worktree-is-untrusted.md", "docs/PLAN.md"]}
      toc={[...themes.map((t) => ({ id: t.id, text: t.title })), { id: "escape", text: "Two escapes, found in an audit" }, { id: "plan", text: "How the plan changed" }]}
    >
      {themes.map((t) => (
        <Section key={t.id} id={t.id} title={t.title} aside={`${t.cases.length} cases`}>
          <p className="fx mb-8 max-w-[68ch] text-[16px] leading-[1.65] text-t2">{t.intro}</p>
          {t.id === "numbers" && (
            <Figure n="1" title="where in the measurement chain each case broke" note="no case broke in the run itself" className="mb-8">
              <WhereNumbersBroke marks={marks} />
            </Figure>
          )}
          <div className="grid gap-3 lg:grid-cols-2">
            {t.cases.map((c) => (
              <Case key={c.title} c={c} n={++n} />
            ))}
          </div>
        </Section>
      ))}

      <Section id="escape" title="Two escapes, found in an audit" aside="ADR 0009">
        <Figure n="2" title="two paths from the container to the host, and what closed each" note="docs/adr/0009-worktree-is-untrusted.md" className="mb-10">
          <Escapes />
        </Figure>
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="fx text-[15.5px] leading-[1.7] text-t2">
            <p>
              Agents ran in a network-less container, but host code — git for diffs and pushes, the grep and code-search
              walks — worked in the same directory afterwards. The 2026-10-16 engineering audit reproduced two escapes
              through it:
            </p>
            <ol className="mt-5 grid gap-3">
              <li className="border-l-2 border-t1 pl-4">
                A <code className="font-mono text-[13px] text-t1">.git</code> swapped for a directory whose config set{" "}
                <code className="font-mono text-[13px] text-t1">core.fsmonitor</code> made the host&apos;s{" "}
                <code className="font-mono text-[13px] text-t1">git diff</code> run a command.
              </li>
              <li className="border-l-2 border-t1 pl-4">
                A symlink to a <code className="font-mono text-[13px] text-t1">.env</code> outside the worktree was returned by the
                host-side grep tool.
              </li>
            </ol>
            <p className="mt-5">It also found the GitHub App token in the push URL — so in argv, persisted errors and traces.</p>
          </div>
          <div className="fx border border-line bg-surface p-6">
            <div className="label text-[10.5px] text-t4">The decision</div>
            <p className="mt-3 text-[17px] font-medium leading-[1.4] tracking-[-0.01em] text-t1">Everything the container can write is hostile input to the host.</p>
            <ul className="mt-5 grid gap-2.5 text-[14.5px] leading-[1.6] text-t2">
              <li>Host git never discovers the repository: it uses a verified worktree admin dir, with hooks and fsmonitor off.</li>
              <li>The container mounts .git read-only, runs as the host user with every capability dropped.</li>
              <li>Host-side walks never follow symlinks; git authenticates through its environment, never a URL.</li>
            </ul>
            <Link href="/design/0009-worktree-is-untrusted/" className="mt-6 inline-block font-mono text-[12px] text-t1 underline decoration-line-2 underline-offset-[3px] hover:decoration-t1">
              ADR 0009 →
            </Link>
          </div>
        </div>
      </Section>

      {amendments.length > 0 && (
        <Section id="plan" title="How the plan changed" aside="docs/PLAN.md §0">
          <p className="fx mb-8 max-w-[68ch] text-[16px] leading-[1.65] text-t2">
            The original spec was written around one vendor&apos;s agent SDK. These amendments replace it where they conflict,
            and the design records and progress log cite them by number.
          </p>
          <ol className="border-t border-line-strong">
            {amendments.map((a) => (
              <li key={a.id + a.decision.slice(0, 20)} className="fx grid gap-2 border-b border-line py-5 md:grid-cols-[72px_minmax(0,1fr)_260px] md:gap-8">
                <span className="font-mono text-[12px] text-t1">{a.id}</span>
                <span className="text-[15px] leading-[1.6] text-t2">{inline(a.decision, "docs/PLAN.md")}</span>
                <span className="font-mono text-[11.5px] leading-[1.6] text-t3">{inline(a.where, "docs/PLAN.md")}</span>
              </li>
            ))}
          </ol>
        </Section>
      )}
    </ChapterPage>
  );
}
