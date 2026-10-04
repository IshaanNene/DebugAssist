// Hidden test for BUG-001 (never committed to the target repo). Copied to test/ at eval time.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EtaPoller } from "../src/eta/poller";

function fakeDoc() {
  const listeners = new Set<() => void>();
  return {
    visibilityState: "visible" as DocumentVisibilityState,
    addEventListener: (_: string, l: () => void) => listeners.add(l),
    removeEventListener: (_: string, l: () => void) => listeners.delete(l),
    set(state: DocumentVisibilityState) {
      this.visibilityState = state;
      for (const l of listeners) l();
    },
  };
}

describe("EtaPoller while backgrounded (hidden)", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("does not spin: at most ~1 tick per 30 s over 17 minutes hidden", async () => {
    const fetchEta = vi.fn().mockResolvedValue({ etaSeconds: 600, status: "driver_assigned" });
    const doc = fakeDoc();
    const poller = new EtaPoller(fetchEta, () => undefined, { doc: doc as unknown as Document });
    poller.start();
    await vi.advanceTimersByTimeAsync(0);
    doc.set("hidden");
    const before = poller.ticks;
    await vi.advanceTimersByTimeAsync(17 * 60 * 1000);
    expect(poller.ticks - before).toBeLessThanOrEqual(40);
    expect(fetchEta).toHaveBeenCalledTimes(1);
    poller.stop();
  });

  it("never schedules sub-second timers while hidden", async () => {
    const doc = fakeDoc();
    const spy = vi.spyOn(globalThis, "setTimeout");
    const poller = new EtaPoller(vi.fn().mockResolvedValue({ etaSeconds: 300, status: "driver_assigned" }), () => undefined, {
      doc: doc as unknown as Document,
    });
    poller.start();
    await vi.advanceTimersByTimeAsync(0);
    doc.set("hidden");
    spy.mockClear();
    await vi.advanceTimersByTimeAsync(120_000);
    expect(spy.mock.calls.map((c) => c[1] ?? 0).filter((d) => d < 1000)).toEqual([]);
    poller.stop();
    spy.mockRestore();
  });
});
