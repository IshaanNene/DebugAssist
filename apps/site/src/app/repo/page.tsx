import type { Metadata } from "next";
import { ChapterPage, Figure, Section } from "@/components/Page";
import { docFile } from "@/lib/docs";
import { Markdown, inline, outline } from "@/lib/md";

export const metadata: Metadata = {
  title: "On your repository — DebugAssist",
  description: "The DebugAssist GitHub App: label an issue, get a root cause on it and a draft pull request when a fix validates. What it may do, onboarding, operations and what is not done yet.",
};

export default function RepoPage() {
  const d = docFile("docs/github-app.md");
  const [lead, ...rest] = d.intro.split(/\n\n/);
  const flow = rest.join("\n\n");
  const parts = outline(d.body);

  return (
    <ChapterPage
      chapter="/repo/"
      title={
        <>
          Label an issue. <span className="hl">Get a draft PR.</span>
        </>
      }
      lead={inline(lead.replace(/\n/g, " "), d.file)}
      sources={[d.file, "configs/policies/writes.yaml"]}
      toc={[{ id: "flow", text: "From label to pull request" }, ...parts]}
    >
      <Section id="flow" title="From label to pull request" aside="debugassist app poll">
        <Figure n="1" title="one labeled issue, end to end" note="draft pull requests only">
          <div className="prose-da [&_pre]:border-0 [&_pre]:bg-transparent [&_pre]:p-0 [&_pre]:text-[13px] [&_pre]:leading-[1.9] [&_pre]:text-t1">
            <Markdown src={flow} from={d.file} />
          </div>
        </Figure>
      </Section>

      <div className="mx-auto max-w-[820px] pt-24">
        <Markdown src={d.body} from={d.file} skipTitle={false} />
      </div>
    </ChapterPage>
  );
}
