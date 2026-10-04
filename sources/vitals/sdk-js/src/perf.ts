// CPU-busy estimate for the main thread: time spent inside timer/animation callbacks plus the
// excess of long tasks, sampled every second. Browsers expose no CPU counter, so this is an
// estimate of JavaScript execution time, which is what drains battery in a hot loop.
export interface PerfSample {
  t: number; // epoch ms
  busy: number; // 0..1 fraction of the last second spent running JS callbacks
  callbacks: number; // timer/rAF callbacks run in the last second
  longTasks: number;
  hidden: boolean;
  heapMb?: number;
}

type Listener = (s: PerfSample) => void;

export class PerfMonitor {
  private scriptMs = 0;
  private callbacks = 0;
  private longTaskMs = 0;
  private longTasks = 0;
  private listeners = new Set<Listener>();
  private started = false;
  readonly samples: PerfSample[] = [];

  constructor(private readonly maxSamples = 900) {}

  start(win: Window & typeof globalThis = window) {
    if (this.started) return;
    this.started = true;
    const now = () => win.performance.now();
    const wrap = <A extends unknown[]>(fn: (...a: A) => unknown) =>
      (...args: A) => {
        const t0 = now();
        try {
          return fn(...args);
        } finally {
          this.scriptMs += now() - t0;
          this.callbacks += 1;
        }
      };
    const origTimeout = win.setTimeout.bind(win);
    const origInterval = win.setInterval.bind(win);
    const origRaf = win.requestAnimationFrame?.bind(win);
    win.setTimeout = ((h: TimerHandler, ms?: number, ...rest: unknown[]) =>
      origTimeout(typeof h === "function" ? wrap(h as (...a: unknown[]) => unknown) : h, ms, ...rest)) as typeof setTimeout;
    win.setInterval = ((h: TimerHandler, ms?: number, ...rest: unknown[]) =>
      origInterval(typeof h === "function" ? wrap(h as (...a: unknown[]) => unknown) : h, ms, ...rest)) as typeof setInterval;
    if (origRaf) win.requestAnimationFrame = (cb: FrameRequestCallback) => origRaf(wrap(cb));
    try {
      new PerformanceObserver((list) => {
        for (const e of list.getEntries()) {
          this.longTasks += 1;
          this.longTaskMs += Math.max(0, e.duration - 50);
        }
      }).observe({ type: "longtask", buffered: false });
    } catch {
      /* longtask unsupported */
    }
    let last = now();
    origInterval(() => {
      const t = now();
      const elapsed = Math.max(1, t - last);
      last = t;
      const mem = (win.performance as Performance & { memory?: { usedJSHeapSize: number } }).memory;
      const sample: PerfSample = {
        t: Date.now(),
        busy: Math.min(1, (this.scriptMs + this.longTaskMs) / elapsed),
        callbacks: this.callbacks,
        longTasks: this.longTasks,
        hidden: win.document.visibilityState === "hidden",
        heapMb: mem ? Math.round(mem.usedJSHeapSize / 1e5) / 10 : undefined,
      };
      this.scriptMs = this.longTaskMs = 0;
      this.callbacks = this.longTasks = 0;
      this.samples.push(sample);
      if (this.samples.length > this.maxSamples) this.samples.shift();
      for (const l of this.listeners) l(sample);
    }, 1000);
  }

  subscribe(l: Listener): () => void {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  }
}
