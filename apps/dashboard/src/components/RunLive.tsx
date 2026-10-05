"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { PUBLIC_API_URL } from "@/lib/api";
import type { Call, GraphNode, RunSummary } from "@/lib/types";
import { PipelineGraph, type Lane } from "./PipelineGraph";
import { Badge, outcomeTone } from "./ui";

// Live run view: the graph and the call log update over server-sent events while the run is going.
export function RunLive(props: { runId: string; summary: RunSummary; graph: GraphNode[]; calls: Call[]; lanes: Lane[] }) {
  const [graph, setGraph] = useState(props.graph);
  const [summary, setSummary] = useState(props.summary);
  const [calls, setCalls] = useState(props.calls);
  const [live, setLive] = useState(false);
  const [filter, setFilter] = useState("all");
  const router = useRouter();

  useEffect(() => {
    if (props.summary.status !== "running") return;
    const es = new EventSource(`${PUBLIC_API_URL}/api/runs/${props.runId}/stream`);
    es.onopen = () => setLive(true);
    es.addEventListener("graph", (e) => {
      const d = JSON.parse((e as MessageEvent).data) as { summary: RunSummary; graph: GraphNode[] };
      setGraph(d.graph);
      setSummary(d.summary);
    });
    es.addEventListener("call", (e) => {
      const c = JSON.parse((e as MessageEvent).data) as Call;
      setCalls((prev) => (prev.some((p) => p.at === c.at && p.kind === c.kind && p.node === c.node) ? prev : [...prev, c]));
    });
    es.addEventListener("end", () => {
      es.close();
      setLive(false);
      router.refresh(); // pick up the decision ledger, costs and notifications written at the end
    });
    es.onerror = () => setLive(false);
    return () => es.close();
  }, [props.runId, props.summary.status, router]);

  const nodes = useMemo(() => Array.from(new Set(calls.map((c) => c.node))), [calls]);
  const shown = calls.filter((c) => filter === "all" || c.node === filter);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge tone={outcomeTone(summary.outcome ?? summary.status)}>{summary.outcome ?? summary.status}</Badge>
        {live && <Badge tone="blue">live</Badge>}
        <span className="text-muted">
          ${summary.cost_usd.toFixed(4)} LLM · {Math.round(summary.seconds)}s · LLM {summary.llm_mode}
        </span>
      </div>
      <PipelineGraph nodes={graph} lanes={props.lanes} />
      <section className="rounded-lg border border-line bg-panel">
        <div className="flex items-center justify-between border-b border-line p-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Agent calls ({shown.length})</h2>
          <select value={filter} onChange={(e) => setFilter(e.target.value)} className="rounded border border-line bg-bg px-2 py-1 text-xs">
            <option value="all">all agents</option>
            {nodes.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </div>
        <div className="max-h-[420px] overflow-y-auto">
          <table className="w-full text-xs">
            <tbody>
              {shown.map((c, i) => (
                <tr key={i} className="border-b border-line last:border-0">
                  <td className="whitespace-nowrap p-2 font-mono text-muted">{c.at.slice(11, 19)}</td>
                  <td className="whitespace-nowrap p-2 font-mono">{c.node}</td>
                  <td className="p-2 text-muted">t{c.turn ?? "–"}</td>
                  <td className="p-2">
                    {c.kind === "tool" ? (
                      <span>
                        <Badge tone={c.ok === false ? "red" : "gray"}>{c.tool}</Badge>{" "}
                        <span className="font-mono text-muted">{JSON.stringify(c.args ?? {}).slice(0, 140)}</span>
                      </span>
                    ) : c.kind === "model" ? (
                      <span className="text-muted">
                        model · {c.input_tokens ?? 0} in / {c.output_tokens ?? 0} out
                      </span>
                    ) : (
                      <span>
                        <Badge tone="amber">{c.kind}</Badge> {c.reason ?? ""}
                      </span>
                    )}
                  </td>
                  <td className="whitespace-nowrap p-2 text-right text-muted">{c.ms != null ? `${c.ms}ms` : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {shown.length === 0 && <p className="p-4 text-sm text-muted">No agent calls recorded (mock runs use scripted results).</p>}
        </div>
      </section>
    </div>
  );
}
