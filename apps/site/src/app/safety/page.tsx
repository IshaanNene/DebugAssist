import type { Metadata } from "next";
import { TrustBoundaries, WriteGate } from "@/components/figs";
import { ChapterPage, Figure, Section } from "@/components/Page";
import { Safety } from "@/components/Sections";
import { writePolicy } from "@/lib/data";
import { threatModel } from "@/lib/docs";
import { Markdown, inline, outline } from "@/lib/md";

export const metadata: Metadata = {
  title: "Safety — DebugAssist",
  description: "The write policy DebugAssist runs under, and its threat model: assets, actors, trust boundaries, controls and the tests that hold them.",
};

export default function SafetyPage() {
  const policy = writePolicy();
  const tm = threatModel();
  const parts = outline(tm.body);
  const counts = policy.rules.reduce<Record<string, number>>((a, r) => ({ ...a, [r.mode]: (a[r.mode] ?? 0) + 1 }), {});

  return (
    <ChapterPage
      chapter="/safety/"
      title={
        <>
          It can&apos;t touch production <span className="hl">on its own.</span>
        </>
      }
      lead={
        <>
          DebugAssist reads text strangers write, hands it to a model with a shell, and can write to repositories, trackers
          and chat. This page is rendered from the two files that bound that: the write policy, and the threat model.
        </>
      }
      sources={["configs/policies/writes.yaml", tm.file]}
      toc={[{ id: "policy", text: "The write policy" }, { id: "threat-model", text: "Threat model" }, ...parts.map((p) => ({ ...p, text: `— ${p.text}` }))]}
    >
      <Section
        id="policy"
        title="The write policy"
        aside={Object.entries(counts)
          .map(([k, n]) => `${n} ${k.replace("_", " ")}`)
          .join(" · ")}
      >
        <Figure n="1" title="one write through the gate" note="configs/policies/writes.yaml" className="mb-10">
          <WriteGate rules={policy.rules} />
        </Figure>
        <Safety rules={policy.rules} branchPrefix={policy.branchPrefix} />
      </Section>

      <Section id="threat-model" title="Threat model" aside={tm.file}>
        <Figure n="2" title="four boundaries, and the test that holds each" note="Trust boundaries and controls" className="mb-12">
          <TrustBoundaries />
        </Figure>
        <div className="grid gap-10 lg:grid-cols-[260px_minmax(0,1fr)]">
          <div className="fx text-[14.5px] leading-[1.6] text-t3 lg:sticky lg:top-24 lg:self-start">
            <p>{inline(tm.intro.split("\n\n")[0].replace(/\n/g, " "), tm.file)}</p>
          </div>
          <div className="fx min-w-0">
            <Markdown src={tm.body} from={tm.file} skipTitle={false} />
          </div>
        </div>
      </Section>
    </ChapterPage>
  );
}
