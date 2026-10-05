"use client";

import { useState } from "react";
import { PUBLIC_API_URL } from "@/lib/api";

// 👍/👎 + comment on the RCA or one claim; stored as feedback for D18 (P10) and evaluation.
export function Reactions({ runId, target, compact = false }: { runId: string; target: string; compact?: boolean }) {
  const [sent, setSent] = useState<"up" | "down" | null>(null);
  const [comment, setComment] = useState("");
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(reaction: "up" | "down") {
    setError(null);
    try {
      const res = await fetch(`${PUBLIC_API_URL}/api/runs/${runId}/feedback`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ target, reaction, comment }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setSent(reaction);
      setOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed");
    }
  }

  return (
    <span className="inline-flex flex-wrap items-center gap-1 text-xs">
      <button
        aria-label="helpful"
        onClick={() => (compact ? send("up") : setOpen(true))}
        className={`rounded px-1.5 py-0.5 hover:bg-bg ${sent === "up" ? "bg-emerald-500/15" : ""}`}
      >
        👍
      </button>
      <button
        aria-label="wrong"
        onClick={() => setOpen(true)}
        className={`rounded px-1.5 py-0.5 hover:bg-bg ${sent === "down" ? "bg-red-500/15" : ""}`}
      >
        👎
      </button>
      {open && (
        <span className="flex items-center gap-1">
          <input
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="what's wrong / right? (optional)"
            className="w-56 rounded border border-line bg-bg px-2 py-0.5"
          />
          <button onClick={() => send("up")} className="rounded border border-line px-1.5">👍 send</button>
          <button onClick={() => send("down")} className="rounded border border-line px-1.5">👎 send</button>
        </span>
      )}
      {sent && <span className="text-muted">thanks</span>}
      {error && <span className="text-red-500">{error}</span>}
    </span>
  );
}
