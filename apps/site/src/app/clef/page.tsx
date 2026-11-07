import type { Metadata } from "next";
import Link from "next/link";
import { ChapterPage, Figure, Section } from "@/components/Page";
import { liveDecisions, replayDecisions, results, type DecisionMetrics } from "@/lib/data";
import { docSection, templates } from "@/lib/docs";
import { Markdown } from "@/lib/md";

export const metadata: Metadata = {
  title: "Why Clef — DebugAssist",
  description: "Why every judgement call in DebugAssist is a calibrated decision model instead of an LLM's self-reported confidence — how it works inside, what it costs, and where the bet stands today.",
};

const TOC = [
  { id: "bet", text: "The bet" },
  { id: "inside", text: "How a decision runs" },
  { id: "backends", text: "Four backends, one contract" },
  { id: "selective", text: "Confident, and right?" },
  { id: "replay", text: "Against an LLM and rules" },
  { id: "ablation", text: "End to end, without Clef" },
  { id: "open", text: "What is still open" },
];

const DOC = "docs/decisions.md";
const BACKENDS = ["clef", "clef-flash", "llm", "rules"] as const;
const NAME: Record<string, string> = { clef: "Clef", "clef-flash": "Clef-flash", llm: "LLM", rules: "rules" };
const f2 = (x: number | null) => (x === null ? "—" : x.toFixed(2));
const pct = (x: number) => `${Math.round(x * 100)}%`;

// The argument, each point from ADR 0002 or docs/decisions.md.
const BET_BASE: [string, string][] = [
  ["Confidence you can use.", "An LLM's self-reported confidence is poorly calibrated, and its answer has to be parsed out of prose. Clef returns typed probabilities per option, so a threshold means something."],
  ["A threshold, not a vibe.", "Each template carries a policy band: act above τ_high, a safe default below τ_low, escalate in between. Changing behaviour is editing two numbers in a versioned YAML file, reviewed like code."],
  ["Every call on the record.", "Each decision is written to a ledger with its state hash, questions, answers, band, action and cost, then labelled from the catalog — so each D# can be scored on its own, and switched off."],
];

function Bar({ v, ink = true }: { v: number; ink?: boolean }) {
  return (
    <div className="relative h-2 w-full border border-line-strong bg-surface">
      <div className={`absolute inset-y-0 left-0 ${ink ? "bg-t1" : "hatch-ink"}`} style={{ width: pct(v) }} />
    </div>
  );
}

export default function ClefPage() {
  const data = results();
  const live = liveDecisions();
  const replay = replayDecisions();
  const tpl = templates();
  const nameOf = (d: string) => tpl.find((t) => d.startsWith(t.id))?.name ?? d;
  const tauOf = (d: string) => tpl.find((t) => d.startsWith(t.id))?.tauHigh;
  const how = docSection(DOC, "How a decision runs");
  const flow = how.match(/```\n([\s\S]*?)```/)?.[1] ?? "";
  const howRest = how.replace(/```[\s\S]*?```/, "").trim();
  const backends = docSection(DOC, "Backends").split("\n\nOpenRouter")[0];
  const costs = (live?.rows ?? []).map((r) => r.usdPer1k);
  const BET: [string, string][] = [
    ...BET_BASE,
    [
      "Cheap enough to ask everywhere.",
      `Clef at $0.24 and Clef-flash at $0.09 per million input tokens${costs.length ? `: $${Math.min(...costs).toFixed(2)}–$${Math.max(...costs).toFixed(2)} per thousand decisions in the runs — about what the LLM decider costs on the same calls, so the case rests on calibration, not price` : ""}. A circuit breaker falls back to the LLM decider when the service fails.`,
    ],
  ];

  // the replay, by decision, with the winner(s) on accuracy
  const byDecision: Record<string, Partial<Record<(typeof BACKENDS)[number], DecisionMetrics>>> = {};
  for (const r of replay?.rows ?? []) (byDecision[r.decision] ??= {})[r.backend as (typeof BACKENDS)[number]] = r;
  const decisions = Object.keys(byDecision).sort();
  const rulesWin = decisions.filter((d) => {
    const x = byDecision[d];
    return x.rules && x.rules.accuracy > Math.max(x.clef?.accuracy ?? 0, x["clef-flash"]?.accuracy ?? 0, x.llm?.accuracy ?? 0);
  });
  const clefBeatsLlm = decisions.filter((d) => (byDecision[d].clef?.accuracy ?? 0) > (byDecision[d].llm?.accuracy ?? 0));
  const flashBeatsLlm = decisions.filter((d) => (byDecision[d]["clef-flash"]?.accuracy ?? 0) > (byDecision[d].llm?.accuracy ?? 0));

  return (
    <ChapterPage
      chapter="/clef/"
      title={
        <>
          Why a decision model, <span className="hl">and whether it pays.</span>
        </>
      }
      lead={
        <>
          The design&apos;s central bet: small, calibrated decision models make the judgement calls, the LLM only reasons
          and writes code, and deterministic code acts. This page is the case for it, how it works inside — and the
          measurements, including the ones that say the bet has not paid off yet.
        </>
      }
      sources={["docs/adr/0002-decide-reason-act.md", DOC, live ? `evals/reports/${live.report}/decisions.csv` : "", replay ? `evals/reports/${replay.report}/e1.csv` : ""].filter(Boolean)}
      toc={TOC}
    >
      <Section id="bet" title="The bet" aside="ADR 0002">
        <ol className="grid gap-px border border-line bg-line md:grid-cols-2">
          {BET.map(([t, b], i) => (
            <li key={t} className="fx bg-surface p-6" style={{ ["--i" as string]: i * 0.4 }}>
              <span className="font-mono text-[12px] text-t4">{String(i + 1).padStart(2, "0")}</span>
              <h3 className="mt-3 text-[19px] font-medium tracking-[-0.015em] text-t1">{t}</h3>
              <p className="mt-2 text-[15px] leading-[1.6] text-t2">{b}</p>
            </li>
          ))}
        </ol>
        <p className="fx mt-6 max-w-[70ch] text-[14.5px] leading-[1.6] text-t3">
          What it deliberately does not do: replace a hard limit. Max turns and the retry cap stay in code; a decision can
          only stop earlier.
        </p>
      </Section>

      <Section id="inside" title="How a decision runs" aside={DOC}>
        <Figure n="1" title="template → Clef → policy band → ledger" note="packages/decisions">
          <pre className="overflow-x-auto font-mono text-[12px] leading-[1.75] text-t1 sm:text-[12.5px]">{flow}</pre>
        </Figure>
        <div className="fx mt-8 max-w-[80ch]">
          <Markdown src={howRest} from={DOC} />
        </div>
      </Section>

      <Section id="backends" title="Four backends, one contract" aside="the same request, the same Decision back">
        <div className="fx">
          <Markdown src={backends} from={DOC} />
        </div>
      </Section>

      {live && (
        <Section id="selective" title="Confident, and right?" aside={`${live.rows.reduce((a, r) => a + r.n, 0)} live decisions · evals/reports/${live.report}`}>
          <p className="fx max-w-[70ch] text-[15.5px] leading-[1.65] text-t2">
            A calibrated decider earns its keep when it knows when it knows. For every decision the runs logged, labelled
            from the catalog: how often Clef was confident enough to act (its probability at or above the template&apos;s
            τ_high), and how often it was right when it did — next to its accuracy overall.
          </p>
          <div className="fx mt-8 border-t border-line-strong">
            <div className="hidden grid-cols-[minmax(0,1.1fr)_64px_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_120px] gap-6 border-b border-line py-2.5 font-mono text-[10.5px] uppercase tracking-[0.08em] text-t3 lg:grid">
              <span>Decision</span>
              <span className="text-right">n</span>
              <span>Acts (coverage at τ_high)</span>
              <span>Right when it acts</span>
              <span>Right overall</span>
              <span className="text-right">Brier · ECE</span>
            </div>
            {live.rows.map((r) => (
              <div key={r.decision} className="grid gap-x-6 gap-y-2 border-b border-line py-4 lg:grid-cols-[minmax(0,1.1fr)_64px_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_120px] lg:items-center">
                <span>
                  <span className="font-mono text-[12.5px] text-t1">{r.decision.slice(0, 3)}</span>{" "}
                  <span className="text-[14.5px] text-t1">{nameOf(r.decision)}</span>
                  <span className="ml-2 font-mono text-[11px] text-t4">τ {tauOf(r.decision)}</span>
                </span>
                <span className="font-mono text-[12.5px] text-t3 lg:text-right">{r.n}</span>
                {(
                  [
                    [r.coverage, true, "acts"],
                    [r.accuracyAtTau, true, "right when acting"],
                    [r.accuracy, false, "right overall"],
                  ] as [number | null, boolean, string][]
                ).map(([v, ink, l]) => (
                  <span key={l} className="grid grid-cols-[minmax(0,1fr)_48px] items-center gap-3">
                    {v === null ? <span className="font-mono text-[11px] text-t4">—</span> : <Bar v={v} ink={ink} />}
                    <span className="font-mono text-[12.5px] text-t1">
                      {v === null ? "" : pct(v)}
                      <span className="ml-1 text-[10px] text-t4 lg:hidden">{l}</span>
                    </span>
                  </span>
                ))}
                <span className="font-mono text-[12px] text-t3 lg:text-right">
                  {f2(r.brier)} · {f2(r.ece)}
                </span>
              </div>
            ))}
          </div>
          <p className="fx mt-6 max-w-[72ch] text-[14.5px] leading-[1.6] text-t3">
            Read a row as a trade: a decision that acts rarely but is right when it does (high second bar, short first one)
            is doing its job and escalating the rest; one that acts on almost everything at low accuracy is overconfident,
            and its ECE says by how much. Brier and ECE: lower is better.
          </p>
        </Section>
      )}

      {replay && decisions.length > 0 && (
        <Section id="replay" title="Against an LLM and rules" aside={`replay E1 · evals/reports/${replay.report}`}>
          <p className="fx max-w-[70ch] text-[15.5px] leading-[1.65] text-t2">
            Every logged decision re-decided four ways — Clef, Clef-flash, an LLM decider given the same template, and
            hand-written rules — and scored against the catalog.{" "}
            <b className="font-medium text-t1">
              Clef beats the LLM decider on {clefBeatsLlm.length} of {decisions.length} decisions, Clef-flash on {flashBeatsLlm.length}
              {rulesWin.length > 0 && <>, and simple rules beat every model on {rulesWin.map((d) => nameOf(d)).join(" and ")}</>}.
            </b>{" "}
            That is the honest state of the bet.
          </p>
          <div className="fx mt-8 overflow-x-auto border border-line bg-surface">
            <table className="w-full min-w-[760px] border-collapse text-left">
              <thead>
                <tr className="border-b border-line bg-sunk/60 font-mono text-[10.5px] uppercase tracking-[0.08em] text-t3">
                  <th className="px-5 py-3 font-normal">Decision</th>
                  <th className="px-5 py-3 text-right font-normal">n</th>
                  {BACKENDS.map((b) => (
                    <th key={b} className="px-5 py-3 text-right font-normal">
                      {NAME[b]}
                    </th>
                  ))}
                  <th className="px-5 py-3 text-right font-normal">Brier · Clef / LLM</th>
                  <th className="px-5 py-3 text-right font-normal">$ / 1k · Clef / LLM</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line font-mono text-[12.5px]">
                {decisions.map((d) => {
                  const x = byDecision[d];
                  const best = Math.max(...BACKENDS.map((b) => (b === "rules" && !x.rules?.accuracy ? -1 : (x[b]?.accuracy ?? -1))));
                  return (
                    <tr key={d}>
                      <td className="px-5 py-3">
                        <span className="text-t1">{d.slice(0, 3)}</span> <span className="font-sans text-[14px] text-t2">{nameOf(d)}</span>
                      </td>
                      <td className="px-5 py-3 text-right text-t3">{x.clef?.n ?? "—"}</td>
                      {BACKENDS.map((b) => {
                        const v = x[b]?.accuracy;
                        // a rules score of 0 means there is no rule for this decision
                        const none = v === undefined || (b === "rules" && v === 0);
                        return (
                          <td key={b} className="px-5 py-3 text-right">
                            {none ? (
                              <span className="text-t4">—</span>
                            ) : (
                              <span className={v === best ? "border-b-2 border-t1 font-semibold text-t1" : "text-t3"}>{v!.toFixed(2)}</span>
                            )}
                          </td>
                        );
                      })}
                      <td className="px-5 py-3 text-right text-t3">
                        {f2(x.clef?.brier ?? null)} / {f2(x.llm?.brier ?? null)}
                      </td>
                      <td className="px-5 py-3 text-right text-t3">
                        {x.clef?.usdPer1k.toFixed(2)} / {x.llm?.usdPer1k.toFixed(2)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="fx mt-4 font-mono text-[11.5px] text-t4">accuracy against the catalog · underlined: best on that decision · — : no rule exists for it</p>
        </Section>
      )}

      {data.ablation && (
        <Section id="ablation" title="End to end, without Clef" aside={`${data.ablation.arm} · ${data.ablation.bugs} bugs`}>
          <p className="fx max-w-[70ch] text-[15.5px] leading-[1.65] text-t2">
            The same pipeline with the LLM decider making every Clef decision, one run per bug, against each bug&apos;s latest
            Clef runs ({data.ablation.clefSeeds} each). The test the thesis needed — and the one that was run last.
          </p>
          <div className="fx mt-8 grid gap-px border border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
            {data.ablation.lanes.map((l) => (
              <div key={l.label} className="bg-surface p-5">
                <div className="label text-[10.5px] text-t4">{l.label}</div>
                <div className="mt-4 grid gap-2.5">
                  {(
                    [
                      ["with Clef", l.clef, true],
                      ["without", l.noClef, false],
                    ] as [string, number, boolean][]
                  ).map(([k, v, ink]) => (
                    <div key={k} className="grid grid-cols-[64px_minmax(0,1fr)_44px] items-center gap-3 font-mono text-[11.5px]">
                      <span className="text-t3">{k}</span>
                      <Bar v={v} ink={ink} />
                      <span className="text-right text-t1">{pct(v)}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <p className="fx mt-6 max-w-[70ch] text-[14.5px] leading-[1.6] text-t3">
            A small difference, within noise: the gaps come from a handful of single bugs and go both ways. Per-run rows are
            in the{" "}
            <Link className="text-t1 underline decoration-line-2 underline-offset-[3px] hover:decoration-t1" href="/results/#clef">
              lab notebook
            </Link>
            .
          </p>
        </Section>
      )}

      <Section id="open" title="What is still open" aside="docs/LESSONS.md · docs/decisions.md">
        <ul className="border-t border-line">
          {[
            ["Thresholds are initial guesses.", "Every τ in the catalog is an initial guess, not a tuned value; tuning waits for enough labelled decisions per template."],
            ["Recalibration only if it holds out.", "Temperature or isotonic recalibration is enabled only if it improves ECE on held-out decisions — not on the runs it was fitted to."],
            ["Rules still win somewhere.", "Where a hand-written rule beats every model, the template is the next thing to fix, not the rule to delete."],
            ["The first ablation should test the thesis.", "The headline numbers were end-to-end RCA and fix rates, which depend mostly on the LLM; an outside review pointed out the thesis itself was untested. It is now stated first."],
          ].map(([t, b], i) => (
            <li key={t} className="fx grid gap-2 border-b border-line py-5 md:grid-cols-[64px_minmax(0,320px)_minmax(0,1fr)] md:gap-8" style={{ ["--i" as string]: i * 0.3 }}>
              <span className="font-mono text-[12px] text-t4">{String(i + 1).padStart(2, "0")}</span>
              <span className="text-[17px] font-medium tracking-[-0.01em] text-t1">{t}</span>
              <span className="text-[15px] leading-[1.6] text-t2">{b}</span>
            </li>
          ))}
        </ul>
      </Section>
    </ChapterPage>
  );
}
