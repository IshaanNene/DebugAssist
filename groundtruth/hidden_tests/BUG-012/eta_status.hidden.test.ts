// Hidden test for BUG-012 (never committed to the target repo). Copied to gateway/test/ at eval time.
import { describe, expect, it } from "vitest";
import { buildApp } from "../src/app.js";
import type { Backends } from "../src/backends.js";
import { NotificationStore } from "../src/notifications.js";

function backends(status: string): Backends {
  const ride = {
    id: "r1", status, city: "sf",
    pickup: { name: "A", lat: 37.79, lng: -122.39 }, dropoff: { name: "B", lat: 37.62, lng: -122.37 },
    driver: null, distance_km: 19.4, created_at: "2026-10-05T00:00:00Z",
  };
  return {
    places: async () => [],
    requestRide: async () => ride,
    ride: async () => ride,
    eta: async () => ({ ride_id: "r1", status, eta_seconds: 300 }),
    fare: async () => ({ city: "sf", currency: "USD", amount_cents: 1000, surge: 1, distance_km: 1, duration_min: 1 }),
  };
}

async function eta(status: string, notes = new NotificationStore()) {
  const app = buildApp(backends(status), notes);
  const res = await app.yoga.fetch("http://gateway/graphql", {
    method: "POST",
    headers: { "content-type": "application/json", "x-session-id": "s-h", "x-app-version": "1.6.0" },
    body: JSON.stringify({ query: `{ eta(rideId: "r1") { status etaSeconds } }` }),
  });
  return { body: (await res.json()) as { data?: { eta?: { status: string } }; errors?: unknown[] }, notes };
}

describe("ETA for every ride status (hidden)", () => {
  it.each(["in_trip", "searching", "matched"])("answers ETA polls for a ride that is %s", async (status) => {
    const { body, notes } = await eta(status);
    expect(body.errors).toBeUndefined();
    expect(body.data?.eta?.status).toBe(status);
    expect(notes.list("s-h")).toHaveLength(0); // nothing to announce for these statuses
  });

  it("still announces the arriving status", async () => {
    const { notes } = await eta("arriving");
    expect(notes.list("s-h").map((n) => n.kind)).toEqual(["ride.arriving"]);
  });
});
