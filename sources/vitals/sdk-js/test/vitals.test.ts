import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { deviceInfo } from "../src/device";
import * as Vitals from "../src/index";

const PIXEL = "Mozilla/5.0 (Linux; Android 15; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Mobile Safari/537.36";
const IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1";

describe("deviceInfo", () => {
  it("parses Android Chrome", () => {
    expect(deviceInfo(PIXEL, "en-US")).toEqual({ os: "Android 15", browser: "Chrome 141", device: "Pixel 7", locale: "en-US" });
  });
  it("parses iOS Safari", () => {
    expect(deviceInfo(IPHONE, "ar")).toMatchObject({ os: "iOS 18.5", browser: "Safari 18", device: "iPhone", locale: "ar" });
  });
});

describe("urlTemplate", () => {
  it("replaces ids", () => {
    expect(Vitals.urlTemplate("http://x/ride/0f8fad5b-d9cb-469f-a165-70867728950e/eta")).toBe("http://x/ride/:id/eta");
    expect(Vitals.urlTemplate("http://x/items/42")).toBe("http://x/items/:n");
  });
});

describe("background activity", () => {
  const sent: { url: string; body: any }[] = [];
  beforeEach(() => {
    sent.length = 0;
    Vitals._resetForTests();
    Vitals._setTransport(async (url, json) => sent.push({ url, body: JSON.parse(json) }));
  });

  it("reports sustained wakeups while hidden as background_cpu", () => {
    Vitals.init({ endpoint: "http://vitals", app: "a", version: "1", sessionId: "s" });
    Vitals._feedPerf(Array.from({ length: 60 }, (_, i) => ({ t: i * 1000, busy: 0.02, callbacks: 250, longTasks: 0, hidden: true })));
    expect(sent).toHaveLength(1);
    const ev = sent[0]!.body.events[0];
    expect(ev.kind).toBe("perf");
    expect(ev.perf).toMatchObject({ metric: "background_cpu", value: 250, unit: "wakeups/s" });
  });

  it("stays quiet for an idle background app", () => {
    Vitals.init({ endpoint: "http://vitals", app: "a", version: "1", sessionId: "s" });
    Vitals._feedPerf(Array.from({ length: 120 }, (_, i) => ({ t: i * 1000, busy: 0, callbacks: 1, longTasks: 0, hidden: true })));
    expect(sent).toHaveLength(0);
  });
});

describe("crash capture", () => {
  const sent: { url: string; body: any }[] = [];
  beforeEach(() => {
    sent.length = 0;
    Vitals._resetForTests();
    Vitals._setTransport(async (url, json) => sent.push({ url, body: JSON.parse(json) }));
  });
  afterEach(() => vi.restoreAllMocks());

  it("reports a fatal error once with flags, breadcrumbs and device", () => {
    Vitals.init({
      endpoint: "http://vitals",
      app: "miniride-client",
      version: "1.6.1",
      sessionId: "s1",
      getFlags: () => ({ notif_router_v2: true }),
      getCity: () => "sf",
    });
    Vitals.breadcrumb("push", "opened from push", { link: "/ride/1" });
    Vitals.captureException(new TypeError("Cannot read properties of undefined (reading 'riderId')"), { fatal: true });
    Vitals.captureException(new Error("second"), { fatal: true });
    expect(sent).toHaveLength(1);
    const ev = sent[0]!.body.events[0];
    expect(sent[0]!.url).toBe("http://vitals/v1/events");
    expect(ev).toMatchObject({ kind: "crash", app: "miniride-client", version: "1.6.1", session_id: "s1", flags: { notif_router_v2: true } });
    expect(ev.error.type).toBe("TypeError");
    expect(ev.breadcrumbs.at(-1).message).toBe("opened from push");
    expect(ev.device.city).toBe("sf");
    Vitals.startSession();
    expect(sent[1]!.url).toBe("http://vitals/v1/sessions");
    expect(sent[1]!.body.flags).toEqual({ notif_router_v2: true });
  });
});
