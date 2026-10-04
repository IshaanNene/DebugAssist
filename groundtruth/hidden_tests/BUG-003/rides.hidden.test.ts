// Hidden test for BUG-003 (never committed to the target repo). Copied to test/ at eval time.
import { describe, expect, it, vi } from "vitest";
import { requestRide } from "../src/api/rides";

const place = { name: "A", lat: 1, lng: 2 };
const ride = { id: "r1", status: "driver_assigned", city: "sf", pickup: place, dropoff: place, driver: null, distanceKm: 1 };

describe("ride requests on a slow network", () => {
  it("retries with the same idempotency key so the server can deduplicate", async () => {
    const keys: string[] = [];
    let n = 0;
    const fetchImpl = vi.fn(async (_u: unknown, init?: RequestInit) => {
      keys.push(JSON.parse(String(init?.body)).variables.input.idempotencyKey);
      if (++n < 2) throw new DOMException("signal timed out", "TimeoutError");
      return new Response(JSON.stringify({ data: { requestRide: ride } }));
    }) as unknown as typeof fetch;
    await requestRide({ city: "sf", pickup: place, dropoff: place }, { fetchImpl });
    expect(new Set(keys).size).toBe(1);
  });

  it("waits longer than matching takes at 2 s of network latency", async () => {
    let timeout = 0;
    const fetchImpl = vi.fn(async (_u: unknown, init?: RequestInit) => {
      timeout = (init?.signal as AbortSignal & { reason?: unknown }) ? 1 : 0;
      return new Response(JSON.stringify({ data: { requestRide: ride } }));
    }) as unknown as typeof fetch;
    const spy = vi.spyOn(AbortSignal, "timeout");
    await requestRide({ city: "sf", pickup: place, dropoff: place }, { fetchImpl });
    expect(timeout).toBe(1);
    expect(spy.mock.calls[0]![0]).toBeGreaterThanOrEqual(10_000);
    spy.mockRestore();
  });
});
