import type { Metadata } from "next";
import { CaseAnatomy, HowEntriesClose } from "@/components/figs";
import { ChapterPage, Figure, Section } from "@/components/Page";
import { docFile, docSection, lessons } from "@/lib/docs";
import { Markdown, inline, outline, parse } from "@/lib/md";

export const metadata: Metadata = {
  title: "Lessons learned — DebugAssist",
  description: "Every problem that cost real time while building DebugAssist: what we saw, why, what fixed it, and the guard that stops it coming back.",
};

const PATTERNS = "Patterns worth keeping";

export default function LessonsPage() {
  const d = docFile("docs/LESSONS.md");
  const [lead, ...introRest] = d.intro.split(/\n\n/);
  const patterns = parse(docSection(d.file, PATTERNS)).flatMap((b) => (b.t === "ol" ? b.items : []));
  // the numbered chapters, without the patterns (shown first, on their own)
  const body = d.body.slice(0, d.body.search(new RegExp(`^## ${PATTERNS}`, "m")));
  const parts = outline(body);
  const entries = (body.match(/^- \*\*/gm) ?? []).length;

  return (
    <ChapterPage
      chapter="/lessons/"
      title={
        <>
          What broke, <span className="hl">and what stops it now.</span>
        </>
      }
      lead={inline(lead.replace(/\n/g, " "), d.file)}
      sources={[d.file]}
      toc={[{ id: "shape", text: "The shape of an entry" }, { id: "patterns", text: PATTERNS }, ...parts]}
    >
      <Section id="shape" title="The shape of an entry" aside={`${lessons().length} entries · ${d.file}`}>
        <Figure n="1" title="symptom → cause → fix → guard" note="one bullet in the log">
          <CaseAnatomy />
        </Figure>
        <Figure n="2" title="how each section's entries close" note="counted from the log at build time" className="mt-10">
          <div className="p-5 sm:p-8">
            <HowEntriesClose entries={lessons()} />
          </div>
        </Figure>
      </Section>

      <Section id="patterns" title={PATTERNS} aside={`${patterns.length} patterns · ${entries} entries below`}>
        <ol className="border-t border-line">
          {patterns.map((p, i) => {
            // "**Title.** body" splits into a title and a body; "**Title**, rest" stays one sentence
            const hit = p.match(/^\*\*(.+?)\*\*\s*(.*)$/);
            const m = hit && !/^[,;:]/.test(hit[2]) ? hit : null;
            return (
              <li key={i} className="fx grid gap-2 border-b border-line py-6 md:grid-cols-[64px_minmax(0,380px)_minmax(0,1fr)] md:gap-8" style={{ ["--i" as string]: i * 0.3 }}>
                <span className="font-mono text-[12px] text-t4">{String(i + 1).padStart(2, "0")}</span>
                <span className="text-[19px] font-medium leading-[1.35] tracking-[-0.015em] text-t1">{inline(m ? m[1] : p.replace(/\*\*/g, ""), d.file)}</span>
                {m && <span className="text-[15px] leading-[1.65] text-t2">{inline(m[2], d.file)}</span>}
              </li>
            );
          })}
        </ol>
      </Section>

      <div className="grid gap-10 pt-24 lg:grid-cols-[240px_minmax(0,1fr)]">
        <aside className="lg:sticky lg:top-24 lg:self-start">
          <div className="label text-[10.5px] text-t4">How to read an entry</div>
          <div className="mt-3 text-[14px] leading-[1.6] text-t3">
            {introRest.map((p, i) => (
              <p key={i} className="mt-2">
                {inline(p.replace(/\n/g, " "), d.file)}
              </p>
            ))}
          </div>
        </aside>
        <div className="max-w-[820px]">
          <Markdown src={body} from={d.file} skipTitle={false} />
        </div>
      </div>
    </ChapterPage>
  );
}
