import type { Metadata } from "next";
import Link from "next/link";
import { ChapterPage, Figure, Section } from "@/components/Page";
import { doc } from "@/components/ui";
import { templates, type Template } from "@/lib/docs";

export const metadata: Metadata = {
  title: "Decisions — DebugAssist",
  description: "Every judgement call in DebugAssist as a calibrated probability: the eighteen Clef decision templates, their thresholds and outcomes.",
};

const TOC = [
  { id: "band", text: "From probability to action" },
  { id: "kinds", text: "Three kinds of question" },
  { id: "catalog", text: "The catalog" },
];

const pct = (x: number) => `${(x * 100).toFixed(1)}%`;

/** A 0–1 strip with the three bands: safe default (hatched), escalate (open), act (ink). */
function BandStrip({ lo, hi, big = false }: { lo: number; hi: number; big?: boolean }) {
  return (
    <div className={`relative w-full ${big ? "h-10" : "h-2.5"} border border-t1`} aria-label={`safe default up to ${lo}, act from ${hi}`}>
      <div className="hatch-ink absolute inset-y-0 left-0" style={{ width: pct(lo) }} />
      <div className="absolute inset-y-0 bg-t1" style={{ left: pct(hi), right: 0 }} />
    </div>
  );
}

function Outcome({ t }: { t: Template }) {
  if (typeof t.act === "string") return <span className="font-mono text-t1">{t.act}</span>;
  return (
    <span className="grid gap-0.5">
      {t.act.map(([k, v]) => (
        <span key={k} className="font-mono">
          <span className="text-t3">{k === "*" ? "any other" : k} →</span> <span className="text-t1">{v}</span>
        </span>
      ))}
    </span>
  );
}

export default function DecisionsPage() {
  const tpl = templates();
  const flash = tpl.filter((t) => t.model === "clef-flash").length;
  const qs = tpl.reduce((a, t) => a + t.questions.length, 0);

  return (
    <ChapterPage
      chapter="/decisions/"
      title={
        <>
          Every judgement call <span className="hl">is a probability.</span>
        </>
      }
      lead={
        <>
          Whether to page someone, which file holds the bug, whether to retry, whether to ship: each is a versioned template
          answered by Clef with a calibrated probability, never a model&apos;s self-reported confidence. A policy band turns
          that probability into one of three named outcomes, and every call is written to a decision ledger.
        </>
      }
      sources={["packages/decisions/templates/", "packages/decisions/src/debugassist/decisions/policy.py", "docs/adr/0002-decide-reason-act.md"]}
      toc={TOC}
    >
      <Section id="band" title="From probability to action" aside="policy.py · apply_policy">
        <Figure n="1" title="one template, three bands" note="D01 triage, as configured">
          {(() => {
            const t = tpl[0];
            return (
              <div className="mx-auto max-w-[880px]">
                <div className="grid grid-cols-3 gap-4 pb-4 font-mono text-[11.5px]">
                  <div>
                    <div className="text-t1">safe default</div>
                    <div className="text-t3">p ≤ τ_low</div>
                    <div className="mt-1 text-t2">→ {t.safeDefault}</div>
                  </div>
                  <div className="text-center">
                    <div className="text-t1">escalate</div>
                    <div className="text-t3">τ_low &lt; p &lt; τ_high</div>
                    <div className="mt-1 text-t2">→ {t.escalate}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-t1">act</div>
                    <div className="text-t3">p ≥ τ_high</div>
                    <div className="mt-1 text-t2">→ {typeof t.act === "string" ? t.act : "per option"}</div>
                  </div>
                </div>
                <BandStrip lo={t.tauLow} hi={t.tauHigh} big />
                <div className="relative mt-2 h-10 font-mono text-[11px] text-t3">
                  {[
                    [0, "0"],
                    [t.tauLow, `τ_low ${t.tauLow}`],
                    [t.tauHigh, `τ_high ${t.tauHigh}`],
                    [1, "1"],
                  ].map(([x, l]) => (
                    <span
                      key={String(l)}
                      className="absolute top-0 flex flex-col items-center whitespace-nowrap"
                      style={{ left: pct(Number(x)), transform: Number(x) === 0 ? "none" : Number(x) === 1 ? "translateX(-100%)" : "translateX(-50%)" }}
                    >
                      <span className="h-2 w-px bg-t1" />
                      <span className="mt-1">{l}</span>
                    </span>
                  ))}
                </div>
                <p className="mt-6 max-w-[64ch] text-[14.5px] leading-[1.6] text-t2">
                  The probability that drives the band depends on the question: for a yes/no (<code className="font-mono text-[12.5px]">noul</code>)
                  it is P(yes); for a <code className="font-mono text-[12.5px]">choice</code>, the probability of the chosen option;
                  for a <code className="font-mono text-[12.5px]">score</code>, the expected level scaled to [0, 1]. Hard caps — max
                  turns, the retry limit — are never removed in favour of a decision.
                </p>
              </div>
            );
          })()}
        </Figure>
      </Section>

      <Section id="kinds" title="Three kinds of question" aside={`${qs} questions across ${tpl.length} templates`}>
        <div className="grid gap-px border border-line bg-line md:grid-cols-3">
          {[
            ["noul", "A yes/no with a probability.", "Is this worth an agent run? Is each claim supported by its evidence? Did the deploy resolve it?"],
            ["choice", "One option out of a set, each with a probability.", "Which root-cause category? Which file holds the bug? Ship a PR, a draft, a report or escalate?"],
            ["score", "A level on an ordered scale.", "Priority from P4 to P0; severity from cosmetic to data loss."],
          ].map(([k, d, e], i) => (
            <div key={k} className="fx bg-surface p-6" style={{ ["--i" as string]: i }}>
              <div className="font-mono text-[13px] text-t1">{k}</div>
              <p className="mt-3 text-[15px] font-medium text-t1">{d}</p>
              <p className="mt-2 text-[14px] leading-[1.6] text-t3">{e}</p>
              <p className="mt-4 font-mono text-[11px] text-t4">
                used {tpl.reduce((a, t) => a + t.questions.filter((q) => q.type === k).length, 0)}×
              </p>
            </div>
          ))}
        </div>
        <p className="fx mt-6 max-w-[70ch] text-[14.5px] leading-[1.6] text-t3">
          {tpl.length - flash} templates run on Clef and {flash} on the faster Clef-flash. Whether Clef earns its place is
          measured, not assumed: every logged decision is replayed against an LLM decider and simple rules in the{" "}
          <Link className="text-t1 underline decoration-line-2 underline-offset-[3px] hover:decoration-t1" href="/results/#clef">
            lab notebook
          </Link>
          .
        </p>
      </Section>

      <Section id="catalog" title="The catalog" aside="open a row for its questions">
        <div className="fx hidden grid-cols-[64px_minmax(0,1.5fr)_150px_minmax(0,1fr)_minmax(0,1.1fr)] gap-4 border-b border-line-strong pb-2 font-mono text-[10.5px] uppercase tracking-[0.08em] text-t3 lg:grid">
          <span>ID</span>
          <span>Decision</span>
          <span>Band</span>
          <span>Escalate · default</span>
          <span>Act</span>
        </div>
        <div>
          {tpl.map((t) => (
            <details key={t.id} id={t.id} className="group scroll-mt-24 border-b border-line">
              <summary className="grid cursor-pointer list-none gap-x-4 gap-y-2 py-5 transition-colors hover:bg-sunk/40 lg:grid-cols-[64px_minmax(0,1.5fr)_150px_minmax(0,1fr)_minmax(0,1.1fr)]">
                <span className="font-mono text-[13px] text-t1">{t.id}</span>
                <span>
                  <span className="flex flex-wrap items-baseline gap-x-3">
                    <span className="text-[16px] font-medium tracking-[-0.01em] text-t1">{t.name[0].toUpperCase() + t.name.slice(1)}</span>
                    <span className="font-mono text-[11px] text-t3">
                      {t.stage} · {t.model}
                      {t.perItem ? " · per item" : ""}
                    </span>
                  </span>
                  <span className="mt-1 block text-[14px] leading-[1.55] text-t2">{t.description}</span>
                </span>
                <span className="self-start pt-1">
                  <BandStrip lo={t.tauLow} hi={t.tauHigh} />
                  <span className="mt-1.5 flex justify-between font-mono text-[10.5px] text-t3">
                    <span>{t.tauLow}</span>
                    <span>{t.tauHigh}</span>
                  </span>
                </span>
                <span className="grid content-start gap-0.5 font-mono text-[12px]">
                  <span>
                    <span className="text-t3">escalate →</span> <span className="text-t1">{t.escalate}</span>
                  </span>
                  <span>
                    <span className="text-t3">default →</span> <span className="text-t1">{t.safeDefault}</span>
                  </span>
                </span>
                <span className="flex items-start justify-between gap-3 text-[12px]">
                  <Outcome t={t} />
                  <span aria-hidden className="grid h-6 w-6 shrink-0 place-items-center border border-line font-mono text-[13px] text-t3 transition-transform group-open:rotate-45">
                    +
                  </span>
                </span>
              </summary>
              <div className="grid gap-3 pb-7 lg:pl-[80px]">
                <div className="font-mono text-[11px] text-t3">
                  gate question: <span className="text-t1">{t.gate}</span> ·{" "}
                  <a className="underline decoration-line-2 underline-offset-[3px] hover:text-t1" href={doc(t.file)}>
                    {t.file.split("/").pop()}
                  </a>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  {t.questions.map((q) => (
                    <div key={q.name} className={`border bg-surface p-4 ${q.name === t.gate ? "border-t1" : "border-line"}`}>
                      <div className="flex items-baseline justify-between gap-3">
                        <span className="font-mono text-[12.5px] text-t1">{q.name}</span>
                        <span className="border border-line-2 px-1.5 py-px font-mono text-[10.5px] text-t3">{q.type}</span>
                      </div>
                      <p className="mt-2 text-[13.5px] leading-[1.55] text-t2">{q.instructions}</p>
                      {typeof q.criteria === "string"
                        ? q.criteria && <p className="mt-3 font-mono text-[11px] text-t3">options supplied at call time: {q.criteria}</p>
                        : q.criteria.length > 0 && (
                            <ol className="mt-3 grid gap-1 border-t border-line pt-3 text-[12.5px] leading-[1.45]">
                              {q.criteria.map((c, n) => (
                                <li key={c.k} className="flex gap-2">
                                  <span className="w-4 shrink-0 font-mono text-[10.5px] leading-[18px] text-t4">{n}</span>
                                  <span>
                                    <span className={c.d ? "font-mono text-[11.5px] text-t1" : "text-t2"}>{c.k}</span>
                                    {c.d && <span className="text-t3"> — {c.d}</span>}
                                  </span>
                                </li>
                              ))}
                            </ol>
                          )}
                    </div>
                  ))}
                </div>
              </div>
            </details>
          ))}
        </div>
      </Section>
    </ChapterPage>
  );
}
