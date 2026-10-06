// Hidden test for BUG-013 (never committed to the target repo). Copied to gateway/test/ at eval time.
import { afterEach, describe, expect, it, vi } from "vitest";
import { buildApp } from "../src/app.js";
import { httpBackends } from "../src/backends.js";

afterEach(() => vi.unstubAllGlobals());

describe("ETA from the real dispatch response shape (hidden)", () => {
  it("passes dispatch's eta_seconds through to the GraphQL etaSeconds field", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ ride_id: "r1", status: "driver_assigned", eta_seconds: 240 }), { status: 200 })),
    );
    const app = buildApp(httpBackends("http://dispatch", "http://payments"));
    const res = await app.yoga.fetch("http://gateway/graphql", {
      method: "POST",
      headers: { "content-type": "application/json", "x-session-id": "s-h", "x-app-version": "1.6.0" },
      body: JSON.stringify({ query: `{ eta(rideId: "r1") { rideId status etaSeconds } }` }),
    });
    const body = (await res.json()) as { data?: { eta: { rideId: string; etaSeconds: number | null } } };
    expect(body.data?.eta).toEqual({ rideId: "r1", status: "driver_assigned", etaSeconds: 240 });
  });
});
