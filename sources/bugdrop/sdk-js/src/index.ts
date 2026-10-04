// BugDrop SDK: "Report a bug" for MiniRide. Captures the user's description and images plus
// metadata, ring-buffered logs (network, analytics, console, GraphQL, UI state, performance) and
// a screenshot of the app's own DOM — never the OS screen.
import { toPng } from "html-to-image";
import { redactDeep, redactText } from "./redact";
import { Ring } from "./ring";

export { redactText } from "./redact";

export interface UiState {
  route: string;
  visibility: DocumentVisibilityState;
  [slice: string]: unknown;
}

export interface BugDropConfig {
  endpoint: string; // e.g. http://localhost:8200
  app: string;
  version: string;
  sessionId: string;
  analyticsId?: string;
  getUiState: () => UiState;
  getFlags?: () => Record<string, boolean>;
  getCity?: () => string | undefined;
  getDevice?: () => { os?: string; browser?: string; device?: string; locale?: string };
  screenshotTarget?: () => HTMLElement | null;
}

type Entry = Record<string, unknown> & { ts: number };

const rings = {
  network: new Ring<Entry>(200),
  analytics: new Ring<Entry>(500),
  console: new Ring<Entry>(300),
  graphql: new Ring<Entry>(200),
  ui_state: new Ring<Entry>(300),
  perf: new Ring<Entry>(900),
};
export type LogKind = keyof typeof rings;

let cfg: BugDropConfig | null = null;
const now = () => Date.now() / 1000;
const UUIDish = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi;

function template(url: string): string {
  try {
    const u = new URL(url, location.href);
    return `${u.origin}${u.pathname.replace(UUIDish, ":id")}`;
  } catch {
    return url;
  }
}

export function record(kind: LogKind, entry: Record<string, unknown>) {
  rings[kind].push({ ts: now(), ...entry });
}

export function recordAnalytics(e: { name: string; ts?: number; props?: Record<string, unknown> }) {
  rings.analytics.push({ ts: e.ts ? e.ts / 1000 : now(), name: e.name, props: e.props ?? {} });
}

export function recordPerf(s: Record<string, unknown> & { t?: number }) {
  rings.perf.push({ ts: s.t ? s.t / 1000 : now(), ...s });
}

export function snapshotUiState(reason: string) {
  if (!cfg) return;
  try {
    rings.ui_state.push({ ts: now(), reason, ...cfg.getUiState() });
  } catch {
    /* app state unavailable (e.g. before hydration) */
  }
}

function networkProfile(): Record<string, unknown> {
  const c = (navigator as Navigator & { connection?: { effectiveType?: string; rtt?: number; downlink?: number; saveData?: boolean } }).connection;
  return c ? { effectiveType: c.effectiveType, rtt: c.rtt, downlink: c.downlink, saveData: c.saveData } : {};
}

export function init(config: BugDropConfig) {
  if (cfg) return;
  cfg = config;
  const origFetch = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (url.startsWith(config.endpoint)) return origFetch(input, init);
    const method = init?.method ?? (input instanceof Request ? input.method : "GET");
    const t0 = performance.now();
    let opName: string | undefined;
    if (url.includes("/graphql") && typeof init?.body === "string") {
      try {
        opName = (JSON.parse(init.body) as { operationName?: string }).operationName;
      } catch {
        /* not JSON */
      }
    }
    try {
      const res = await origFetch(input, init);
      const ms = Math.round(performance.now() - t0);
      record("network", { method, url: template(url), status: res.status, ms });
      if (opName !== undefined) {
        void res
          .clone()
          .json()
          .then((b: { errors?: { extensions?: { code?: string }; message: string }[] }) =>
            record("graphql", { operationName: opName, status: res.status, ms, errors: (b.errors ?? []).map((e) => e.extensions?.code ?? e.message) }),
          )
          .catch(() => record("graphql", { operationName: opName, status: res.status, ms, errors: [] }));
      }
      return res;
    } catch (err) {
      const ms = Math.round(performance.now() - t0);
      const error = err instanceof Error ? `${err.name}: ${err.message}` : String(err);
      record("network", { method, url: template(url), status: 0, ms, error });
      if (opName !== undefined) record("graphql", { operationName: opName, status: 0, ms, errors: [error] });
      throw err;
    }
  };
  for (const level of ["log", "info", "warn", "error"] as const) {
    const orig = console[level].bind(console);
    console[level] = (...args: unknown[]) => {
      record("console", { level, message: args.map((a) => (typeof a === "string" ? a : safe(a))).join(" ").slice(0, 500) });
      orig(...args);
    };
  }
  document.addEventListener("visibilitychange", () => snapshotUiState("visibilitychange"));
  addEventListener("popstate", () => snapshotUiState("navigation"));
  for (const method of ["pushState", "replaceState"] as const) {
    const orig = history[method].bind(history);
    history[method] = (data: unknown, unused: string, url?: string | URL | null) => {
      orig(data, unused, url);
      queueMicrotask(() => snapshotUiState("navigation"));
    };
  }
  setInterval(() => snapshotUiState("interval"), 15_000);
  snapshotUiState("init");
}

function safe(v: unknown): string {
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}

export interface Submission {
  description: string;
  attachments?: Blob[];
}

const isReporterUi = (node: HTMLElement) =>
  !(node.classList?.contains("bd-fab") || node.classList?.contains("bd-backdrop"));

export async function captureScreenshot(): Promise<Blob | null> {
  let el = cfg?.screenshotTarget?.() ?? document.getElementById("root");
  // A crashed app can leave its root empty (blank screen): capture the page itself instead.
  if (!el || el.getBoundingClientRect().height < 1) el = document.body;
  try {
    const dataUrl = await toPng(el, {
      pixelRatio: 1,
      cacheBust: true,
      backgroundColor: getComputedStyle(document.body).backgroundColor,
      width: Math.max(el.clientWidth, 1),
      height: Math.max(el.clientHeight, window.innerHeight, 1),
      filter: isReporterUi,
    });
    if (!dataUrl.startsWith("data:image/png;base64,") || dataUrl.length < 100) return null;
    const blob = await (await fetch(dataUrl)).blob();
    return blob.size > 0 ? blob : null;
  } catch {
    return null;
  }
}

export function buildReport(description: string): Record<string, unknown> {
  if (!cfg) throw new Error("BugDrop not initialised");
  snapshotUiState("report");
  const logs = Object.fromEntries(Object.entries(rings).map(([k, r]) => [k, r.toArray()]));
  const ui = cfg.getUiState();
  return redactDeep({
    description: redactText(description),
    app: cfg.app,
    version: cfg.version,
    session_id: cfg.sessionId,
    analytics_id: cfg.analyticsId,
    device: cfg.getDevice?.() ?? {},
    city: cfg.getCity?.(),
    route: ui.route,
    flags: cfg.getFlags?.() ?? {},
    network: networkProfile(),
    logs,
    created_at: now(),
  });
}

export async function submit({ description, attachments = [] }: Submission, transport: typeof fetch = fetch): Promise<{ id: string }> {
  if (!cfg) throw new Error("BugDrop not initialised");
  const form = new FormData();
  form.set("report", JSON.stringify(buildReport(description)));
  const shot = await captureScreenshot();
  if (shot) form.set("screenshot", shot, "screenshot.png");
  for (const [i, a] of attachments.slice(0, 4).entries()) form.append("attachments", a, (a as File).name ?? `attachment-${i}.png`);
  const res = await transport(`${cfg.endpoint}/v1/reports`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`BugDrop upload failed (${res.status})`);
  return (await res.json()) as { id: string };
}

// ---- reporter UI ------------------------------------------------------------------------------

const CSS = `
.bd-fab{position:fixed;right:16px;bottom:88px;z-index:2147483000;border:0;border-radius:999px;padding:10px 14px;background:#d97706;color:#fff;font:600 13px system-ui;box-shadow:0 4px 14px rgb(0 0 0/.25);cursor:pointer}
.bd-backdrop{position:fixed;inset:0;background:rgb(0 0 0/.45);z-index:2147483001;display:flex;align-items:flex-end;justify-content:center}
.bd-sheet{background:#fff;color:#1c1917;width:100%;max-width:480px;border-radius:16px 16px 0 0;padding:20px;display:flex;flex-direction:column;gap:10px;font:14px system-ui}
.bd-sheet textarea{min-height:96px;font:inherit;padding:10px;border-radius:10px;border:1px solid #d6d3d1}
.bd-row{display:flex;gap:8px;justify-content:flex-end}.bd-row button{font:600 14px system-ui;padding:10px 14px;border-radius:10px;border:0;cursor:pointer}
.bd-send{background:#d97706;color:#fff}.bd-cancel{background:#f5f5f4}
`;

export function mountButton(label = "Report a bug") {
  if (document.querySelector(".bd-fab")) return;
  const style = document.createElement("style");
  style.textContent = CSS;
  document.head.appendChild(style);
  const btn = document.createElement("button");
  btn.className = "bd-fab";
  btn.textContent = label;
  btn.dataset.testid = "bugdrop-button";
  btn.addEventListener("click", () => openReporter());
  document.body.appendChild(btn);
}

export function openReporter(): void {
  if (document.querySelector(".bd-backdrop")) return;
  const backdrop = document.createElement("div");
  backdrop.className = "bd-backdrop";
  backdrop.innerHTML = `
    <form class="bd-sheet" role="dialog" aria-label="Report a bug">
      <strong>Report a bug</strong>
      <label>What went wrong?<br><textarea data-testid="bugdrop-description" required></textarea></label>
      <label>Attach screenshots (optional)<br><input data-testid="bugdrop-attach" type="file" accept="image/png,image/jpeg,image/webp" multiple></label>
      <span class="bd-note" style="color:#78716c">We include app logs and a screenshot of this app (not your other apps).</span>
      <div class="bd-row"><button type="button" class="bd-cancel">Cancel</button><button type="submit" class="bd-send" data-testid="bugdrop-submit">Send</button></div>
    </form>`;
  const form = backdrop.querySelector("form")!;
  const close = () => backdrop.remove();
  backdrop.querySelector(".bd-cancel")!.addEventListener("click", close);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const description = (form.querySelector("textarea") as HTMLTextAreaElement).value.trim();
    const files = Array.from((form.querySelector("input[type=file]") as HTMLInputElement).files ?? []);
    const send = form.querySelector(".bd-send") as HTMLButtonElement;
    send.disabled = true;
    send.textContent = "Sending…";
    backdrop.style.visibility = "hidden"; // keep the sheet out of the app screenshot
    void submit({ description, attachments: files })
      .then(({ id }) => {
        backdrop.style.visibility = "visible";
        form.innerHTML = `<strong data-testid="bugdrop-done">Thanks! Report ${id} sent.</strong><div class="bd-row"><button type="button" class="bd-cancel">Close</button></div>`;
        form.querySelector(".bd-cancel")!.addEventListener("click", close);
      })
      .catch((err: unknown) => {
        backdrop.style.visibility = "visible";
        send.disabled = false;
        send.textContent = "Send";
        console.warn("bugdrop", err);
      });
  });
  document.body.appendChild(backdrop);
}

/** Test helper. */
export function _reset() {
  cfg = null;
  for (const k of Object.keys(rings) as LogKind[]) rings[k] = new Ring(1000) as never;
}
