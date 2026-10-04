// Hidden test for BUG-007 (never committed to the target repo). Copied to gateway/test/ at eval time.
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { httpBackends } from "../src/backends.js";

let server: Server;
let base = "";

beforeAll(async () => {
  server = createServer((req, res) => {
    // Matching takes ~1 s in production (dispatch MATCH_DELAY), longer under load.
    const delay = req.url === "/rides" ? 1500 : 5;
    setTimeout(() => {
      res.writeHead(201, { "content-type": "application/json" });
      res.end(JSON.stringify({ id: "r1", status: "driver_assigned", city: "sf", pickup: {}, dropoff: {}, driver: null, distance_km: 1, created_at: "x" }));
    }, delay);
  });
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});
afterAll(() => server.close());

describe("upstream timeouts", () => {
  it("ride requests wait for matching to finish", async () => {
    const b = httpBackends(base, base);
    const ride = await b.requestRide({ session_id: "s", city: "sf", pickup: { name: "a", lat: 1, lng: 1 }, dropoff: { name: "b", lat: 1, lng: 1 } });
    expect(ride.id).toBe("r1");
  }, 20_000);
});
