// Vitals browser SDK: crashes, hangs, jank and performance degradation, with session
// denominators (flag exposures, version, device) so the service can compute crash rates.
import { deviceInfo, type DeviceInfo } from "./device";
import { PerfMonitor, type PerfSample } from "./perf";

export { PerfMonitor, type PerfSample } from "./perf";

export interface VitalsConfig {
  endpoint: string; // e.g. http://localhost:8100
  app: string;
  version: string;
  sessionId: string;
  analyticsId?: string;
  getFlags?: () => Record<string, boolean>;
  getCity?: () => string | undefined;
  getRoute?: () => string;
  /** Called before a fatal error is reported (e.g. to flush analytics). */
  onCrash?: () => void;
}

interface Breadcrumb {
  ts: number;
  category: string;
  message: string;
  data: Record<string, unknown>;
}

const MAX_BREADCRUMBS = 100;
const MAX_LOGS = 100;
// A backgrounded app should be nearly idle. Sustained JS busy time or frequent timer wakeups
// (each wakeup keeps the CPU out of low-power states) both mean battery drain.
const HIDDEN_BUSY_THRESHOLD = 0.25;
const HIDDEN_WAKEUPS_THRESHOLD = 50; // callbacks per second
const HIDDEN_WINDOW_S = 60;
const HANG_MS = 3000;

let cfg: VitalsConfig | null = null;
let device: DeviceInfo | null = null;
const breadcrumbs: Breadcrumb[] = [];
const logs: { ts: number; level: string; message: string }[] = [];
export const perf = new PerfMonitor();
let hiddenBusyRun: PerfSample[] = [];
let lastPerfReport = 0;
let longTaskWindow: number[] = [];
let crashed = false;

const uuid = () => crypto.randomUUID();
const nowS = () => Date.now() / 1000;
const UUIDish = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi;

export function urlTemplate(url: string): string {
  try {
    const u = new URL(url, location.href);
    return `${u.origin}${u.pathname.replace(UUIDish, ":id").replace(/\/\d+(?=\/|$)/g, "/:n")}`;
  } catch {
    return url;
  }
}

export function breadcrumb(category: string, message: string, data: Record<string, unknown> = {}) {
  breadcrumbs.push({ ts: nowS(), category, message, data });
  if (breadcrumbs.length > MAX_BREADCRUMBS) breadcrumbs.shift();
}

// keepalive lets crash reports survive the page being torn down right after the error.
function send(path: string, body: unknown) {
  if (!cfg) return;
  const json = JSON.stringify(body);
  void transport(`${cfg.endpoint}${path}`, json).catch(() => undefined);
}

let transport = (url: string, json: string): Promise<unknown> =>
  nativeFetch(url, { method: "POST", body: json, headers: { "content-type": "application/json" }, keepalive: json.length < 60_000 });

const nativeFetch: typeof fetch = (...a) => fetch(...a);

function base() {
  const c = cfg!;
  return {
    event_id: uuid(),
    app: c.app,
    platform: "web" as const,
    version: c.version,
    ts: nowS(),
    session_id: c.sessionId,
    analytics_id: c.analyticsId,
    culprit: c.getRoute?.() ?? location.pathname,
    breadcrumbs: breadcrumbs.slice(-50),
    logs: logs.slice(-50),
    flags: c.getFlags?.() ?? {},
    device: { ...device, city: c.getCity?.() },
  };
}

function errorInfo(err: unknown) {
  if (err instanceof Error) return { type: err.name || "Error", message: err.message, stack: err.stack ?? null };
  return { type: "NonError", message: typeof err === "string" ? err : JSON.stringify(err ?? null), stack: null };
}

export function captureException(err: unknown, opts: { fatal?: boolean } = {}) {
  if (!cfg) return;
  const fatal = opts.fatal ?? false;
  if (fatal) {
    if (crashed) return;
    crashed = true;
    cfg.onCrash?.();
  }
  send("/v1/events", { events: [{ ...base(), kind: fatal ? "crash" : "exception", error: errorInfo(err) }] });
}

function capturePerf(kind: "perf" | "hang" | "jank", metric: string, value: number, unit: string, details: Record<string, unknown>, windowS?: number) {
  if (!cfg) return;
  send("/v1/events", { events: [{ ...base(), kind, perf: { metric, value, unit, window_s: windowS, details } }] });
}

/** Report the session start (call once flags are known). Sessions are the crash-rate denominator. */
export function startSession() {
  if (!cfg) return;
  send("/v1/sessions", {
    session_id: cfg.sessionId,
    analytics_id: cfg.analyticsId,
    app: cfg.app,
    platform: "web",
    version: cfg.version,
    flags: cfg.getFlags?.() ?? {},
    device: { ...device, city: cfg.getCity?.() },
  });
}

function onPerfSample(s: PerfSample) {
  // CPU activity while the app is in the background → battery drain.
  if (s.hidden && (s.busy >= HIDDEN_BUSY_THRESHOLD || s.callbacks >= HIDDEN_WAKEUPS_THRESHOLD)) hiddenBusyRun.push(s);
  else hiddenBusyRun = [];
  if (hiddenBusyRun.length >= HIDDEN_WINDOW_S && Date.now() - lastPerfReport > 5 * 60_000) {
    const avg = hiddenBusyRun.reduce((a, x) => a + x.busy, 0) / hiddenBusyRun.length;
    const cps = hiddenBusyRun.reduce((a, x) => a + x.callbacks, 0) / hiddenBusyRun.length;
    lastPerfReport = Date.now();
    breadcrumb("perf", `${Math.round(cps)} timer wakeups/s while hidden (JS busy ${Math.round(avg * 100)}%)`);
    capturePerf("perf", "background_cpu", Math.round(cps), "wakeups/s", {
      js_busy_pct: Math.round(avg * 1000) / 10,
      hidden_for_s: hiddenBusyRun.length,
      samples: hiddenBusyRun.slice(-10),
    }, hiddenBusyRun.length);
    hiddenBusyRun = [];
  }
  // Jank: many long tasks within a minute while visible.
  if (!s.hidden && s.longTasks > 0) {
    longTaskWindow.push(...Array(s.longTasks).fill(s.t));
    longTaskWindow = longTaskWindow.filter((t) => s.t - t < 60_000);
    if (longTaskWindow.length >= 10) {
      capturePerf("jank", "long_tasks", longTaskWindow.length, "per_min", {});
      longTaskWindow = [];
    }
  }
}

export function init(config: VitalsConfig) {
  if (cfg) return;
  cfg = config;
  device = deviceInfo();
  addEventListener("error", (e) => captureException(e.error ?? e.message, { fatal: true }));
  addEventListener("unhandledrejection", (e) => captureException(e.reason, { fatal: true }));
  document.addEventListener("visibilitychange", () => breadcrumb("lifecycle", `app ${document.visibilityState}`));
  addEventListener("popstate", () => breadcrumb("navigation", location.pathname));
  for (const method of ["pushState", "replaceState"] as const) {
    const orig = history[method].bind(history);
    history[method] = (data: unknown, unused: string, url?: string | URL | null) => {
      orig(data, unused, url);
      if (url) breadcrumb("navigation", String(url));
    };
  }
  for (const level of ["warn", "error", "info", "log"] as const) {
    const orig = console[level].bind(console);
    console[level] = (...args: unknown[]) => {
      logs.push({ ts: nowS(), level, message: args.map((a) => (typeof a === "string" ? a : safeJson(a))).join(" ").slice(0, 500) });
      if (logs.length > MAX_LOGS) logs.shift();
      orig(...args);
    };
  }
  const origFetch = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (url.startsWith(config.endpoint)) return origFetch(input, init);
    const t0 = performance.now();
    try {
      const res = await origFetch(input, init);
      const ms = Math.round(performance.now() - t0);
      breadcrumb("http", `${init?.method ?? "GET"} ${urlTemplate(url)} ${res.status}`, { ms });
      return res;
    } catch (err) {
      breadcrumb("http", `${init?.method ?? "GET"} ${urlTemplate(url)} failed`, { ms: Math.round(performance.now() - t0), error: String(err) });
      throw err;
    }
  };
  // Hang detection: a 1 s heartbeat that fires late means the main thread was blocked.
  let expected = performance.now() + 1000;
  setInterval(() => {
    const lag = performance.now() - expected;
    expected = performance.now() + 1000;
    if (lag > HANG_MS && document.visibilityState === "visible") {
      capturePerf("hang", "main_thread_blocked", Math.round(lag), "ms", {});
    }
  }, 1000);
  perf.start();
  perf.subscribe(onPerfSample);
}

function safeJson(v: unknown): string {
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}

/** Test helper: feed perf samples through the background-activity rule. */
export function _feedPerf(samples: PerfSample[]) {
  for (const s of samples) onPerfSample(s);
}

/** Test helper. */
export function _setTransport(t: (url: string, json: string) => Promise<unknown>) {
  transport = t;
}

/** Test helper. */
export function _resetForTests() {
  cfg = null;
  breadcrumbs.length = 0;
  logs.length = 0;
  crashed = false;
  hiddenBusyRun = [];
  lastPerfReport = 0;
}

export function _state() {
  return { breadcrumbs, logs, crashed };
}
