// Vitals SDK for Node services (vendored by DebugAssist's make sync-sdks). No dependencies.
import { randomUUID } from "node:crypto";

interface Config {
  endpoint: string;
  app: string;
  version: string;
}

let cfg: Config | null = null;

export function initVitals(endpoint: string | undefined, app: string, version: string) {
  if (!endpoint || cfg) return;
  cfg = { endpoint: endpoint.replace(/\/$/, ""), app, version };
  process.on("uncaughtExceptionMonitor", (err) => captureException(err, { culprit: "process" }));
}

export function captureException(
  err: unknown,
  opts: { culprit?: string; sessionId?: string; traceId?: string; tags?: Record<string, string> } = {},
) {
  if (!cfg) return;
  const e = err instanceof Error ? err : new Error(String(err));
  const body = {
    events: [
      {
        event_id: randomUUID(),
        kind: "exception",
        app: cfg.app,
        platform: "node",
        version: cfg.version,
        ts: Date.now() / 1000,
        session_id: opts.sessionId,
        culprit: opts.culprit,
        trace_id: opts.traceId,
        tags: opts.tags ?? {},
        error: { type: e.name, message: e.message, stack: e.stack ?? null },
      },
    ],
  };
  void fetch(`${cfg.endpoint}/v1/events`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(5000),
  }).catch(() => undefined);
}
