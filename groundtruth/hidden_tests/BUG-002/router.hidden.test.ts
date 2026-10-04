// Hidden test for BUG-002 (never committed to the target repo). Copied to test/ at eval time.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const flags = vi.hoisted(() => ({ v2: true }));
vi.mock("../src/flags", () => ({ FLAGS: { notifRouterV2: "notif_router_v2" }, flag: () => flags.v2 }));

import { routeDeepLink } from "../src/notifications/router";
import { hydrate, resetSessionForTests } from "../src/store/session";

describe("router v2: tapping a push right after launch", () => {
  beforeEach(() => {
    resetSessionForTests();
    vi.useFakeTimers();
  });
  afterEach(() => vi.useRealTimers());

  it.each([0, 100, 300])("tap %i ms after launch does not throw and lands on the ride", async (tapMs) => {
    const navigate = vi.fn();
    void hydrate({ delayMs: 350 });
    await vi.advanceTimersByTimeAsync(tapMs);
    const routed = routeDeepLink("/ride/abc", navigate, "push");
    await vi.advanceTimersByTimeAsync(400);
    await expect(routed).resolves.toBeUndefined();
    expect(navigate).toHaveBeenCalledTimes(1);
    expect(navigate.mock.calls[0]![0]).toBe("/ride/abc");
  });
});
