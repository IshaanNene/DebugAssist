import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { _resetForTests, _setTransport, init } from "../src/vendor/vitals";

describe("Vitals hang detection", () => {
  const sent: string[] = [];
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["setTimeout", "setInterval", "clearInterval", "clearTimeout", "Date", "performance"] });
    sent.length = 0;
    _resetForTests();
    _setTransport(async (_url, json) => {
      sent.push(json);
    });
  });
  afterEach(() => vi.useRealTimers());

  it("does not report hangs while the main thread is idle", async () => {
    init({ endpoint: "http://vitals.test", app: "miniride-client", version: "test", sessionId: "s1" });
    await vi.advanceTimersByTimeAsync(30_000);
    expect(sent.filter((j) => j.includes('"kind":"hang"'))).toEqual([]);
  });

});
