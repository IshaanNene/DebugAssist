"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { PUBLIC_API_URL } from "@/lib/api";
import { Badge } from "./ui";

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${PUBLIC_API_URL}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = (await res.json()) as T & { detail?: string };
  if (!res.ok) throw new Error(data.detail ?? `HTTP ${res.status}`);
  return data;
}

function Box({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-line bg-panel p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">{title}</h2>
      {children}
    </section>
  );
}

interface DiffFixResult {
  status: string;
  reason?: string;
  commit?: string;
  title?: string;
  summary?: string;
  diff?: string;
  pushed?: boolean;
  commented?: boolean;
}

const PRESETS = ["Add a test for the edge case", "Make the diff smaller", "Follow the surrounding code style", "Explain the change in a code comment"];

export function DiffFixer({ runId }: { runId: string }) {
  const [instruction, setInstruction] = useState("");
  const [job, setJob] = useState<string | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const [result, setResult] = useState<DiffFixResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    if (!job) return;
    const t = setInterval(async () => {
      const res = await fetch(`${PUBLIC_API_URL}/api/runs/${runId}/jobs/${job}`);
      const d = (await res.json()) as { status: string; result?: DiffFixResult; log?: string[] };
      if (d.status === "done" && d.result) {
        setResult(d.result);
        setJob(null);
        router.refresh();
      } else setLog(d.log ?? []);
    }, 3000);
    return () => clearInterval(t);
  }, [job, runId, router]);

  async function start() {
    setError(null);
    setResult(null);
    try {
      const d = await post<{ job: string }>(`/api/runs/${runId}/diff-fix`, { instruction });
      setJob(d.job);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed");
    }
  }

  return (
    <Box title="Diff fixer">
      <div className="flex gap-2">
        <input
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder='e.g. "use the existing helper instead"'
          className="min-w-0 flex-1 rounded border border-line bg-bg px-2 py-1 text-sm"
          disabled={!!job}
        />
        <button onClick={start} disabled={!!job || instruction.trim().length < 3} className="rounded bg-llm px-3 py-1 text-sm text-white disabled:opacity-40">
          {job ? "working…" : "Revise"}
        </button>
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        {PRESETS.map((p) => (
          <button key={p} onClick={() => setInstruction(p)} disabled={!!job} className="rounded border border-line px-1.5 py-0.5 text-xs hover:bg-bg">
            {p}
          </button>
        ))}
      </div>
      {job && (
        <pre className="mt-3 max-h-32 overflow-auto rounded bg-bg p-2 text-[11px] text-muted">
          {log.length ? log.join("\n") : "starting the agent in the sandbox…"}
        </pre>
      )}
      {result && (
        <div className="mt-3 space-y-1 text-sm">
          <Badge tone={result.status === "committed" ? "green" : "red"}>{result.status}</Badge>{" "}
          {result.commit && (
            <span className="font-mono text-xs">
              {result.commit} {result.title}
            </span>
          )}
          {result.reason && <p className="text-xs text-red-500">{result.reason}</p>}
          {result.summary && <p className="text-muted">{result.summary}</p>}
          {result.commit && (
            <p className="text-xs text-muted">
              Re-validated · pushed {result.pushed ? "yes" : "no"} · PR comment {result.commented ? "yes" : "no"}
            </p>
          )}
        </div>
      )}
      {error && <p className="mt-2 text-xs text-red-500">{error}</p>}
    </Box>
  );
}

interface Msg {
  role: "user" | "assistant";
  content: string;
  evidence_ids?: string[];
}

export function AskAi({ runId }: { runId: string }) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [correction, setCorrection] = useState(false);
  const [session, setSession] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  async function send() {
    const message = text.trim();
    if (!message) return;
    setBusy(true);
    setNote(null);
    setMessages((m) => [...m, { role: "user", content: message }]);
    setText("");
    try {
      const d = await post<{ session_id: string; answer: string; evidence_ids: string[]; cost_usd: number; routed?: { kind?: string; action?: string } | null }>(
        `/api/runs/${runId}/ask`,
        { message, session_id: session, correction },
      );
      setSession(d.session_id);
      setMessages((m) => [...m, { role: "assistant", content: d.answer, evidence_ids: d.evidence_ids }]);
      if (d.routed) setNote(`Correction classified by Clef (D18) as ${d.routed.kind} → ${d.routed.action}`);
      setCorrection(false);
    } catch (e) {
      setNote(e instanceof Error ? e.message : "failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Box title="Ask AI">
      <div className="max-h-80 space-y-2 overflow-y-auto">
        {messages.length === 0 && <p className="text-xs text-muted">Ask about the root cause, the evidence or the fix. Answers cite evidence ids.</p>}
        {messages.map((m, i) => (
          <div key={i} className={`rounded p-2 text-sm ${m.role === "user" ? "ml-8 bg-bg" : "mr-8 border border-line"}`}>
            <p className="whitespace-pre-wrap">{m.content}</p>
            {m.evidence_ids && m.evidence_ids.length > 0 && (
              <div className="mt-1 flex flex-wrap gap-1">
                {m.evidence_ids.map((e) => (
                  <span key={e} className="font-mono text-[10px] text-muted">{e}</span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="mt-2 flex gap-2">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !busy && send()}
          placeholder="Why did it take 17 minutes to notice?"
          className="min-w-0 flex-1 rounded border border-line bg-bg px-2 py-1 text-sm"
          disabled={busy}
        />
        <button onClick={send} disabled={busy || !text.trim()} className="rounded bg-llm px-3 py-1 text-sm text-white disabled:opacity-40">
          {busy ? "…" : "Ask"}
        </button>
      </div>
      <label className="mt-2 flex items-center gap-2 text-xs text-muted">
        <input type="checkbox" checked={correction} onChange={(e) => setCorrection(e.target.checked)} />
        this corrects the analysis (route it through the feedback loop)
      </label>
      {note && <p className="mt-1 text-xs text-muted">{note}</p>}
      {session && <p className="mt-1 font-mono text-[10px] text-muted">session {session}</p>}
    </Box>
  );
}

interface OpenEnv {
  vscode: string;
  devcontainer: string;
  commands: string[];
  bad_ref: string;
  fix_branch: string;
  flags: Record<string, unknown>;
  test_command: string;
}

export function OpenInMachine({ runId }: { runId: string }) {
  const [env, setEnv] = useState<OpenEnv | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function open() {
    setError(null);
    try {
      const d = await post<OpenEnv>(`/api/runs/${runId}/open`);
      setEnv(d);
      window.location.href = d.vscode;
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed");
    }
  }

  return (
    <Box title="Open in your machine">
      <button onClick={open} className="rounded border border-line px-3 py-1 text-sm hover:bg-bg">
        Open in VS Code
      </button>
      {env && (
        <div className="mt-3 space-y-1 text-xs">
          <p>
            Bad release <span className="font-mono">{env.bad_ref}</span> · fix branch <span className="font-mono">{env.fix_branch}</span> · flags{" "}
            <span className="font-mono">{JSON.stringify(env.flags)}</span>
          </p>
          <p className="text-muted">
            devcontainer: <span className="font-mono">{env.devcontainer}</span>
          </p>
          {env.commands.map((c) => (
            <pre key={c} className="overflow-x-auto rounded bg-bg p-1.5 font-mono">$ {c}</pre>
          ))}
        </div>
      )}
      {error && <p className="mt-2 text-xs text-red-500">{error}</p>}
    </Box>
  );
}
