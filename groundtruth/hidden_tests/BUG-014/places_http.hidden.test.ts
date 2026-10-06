// Hidden test for BUG-014 (never committed to the target repo). Copied to gateway/test/ at eval time.
import { afterEach, describe, expect, it, vi } from "vitest";
import { buildApp } from "../src/app.js";
import { httpBackends } from "../src/backends.js";

afterEach(() => vi.unstubAllGlobals());

describe("places keep their ids (hidden)", () => {
  it("returns the id clients select places by", async () => {
    const dispatchPlaces = [
      { id: "sf-ferry", name: "Ferry Building", lat: 37.7955, lng: -122.3937, rank: 1 },
      { id: "sf-sfo", name: "SFO Airport", lat: 37.6213, lng: -122.379, rank: 3 },
    ];
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(dispatchPlaces), { status: 200 })));
    const app = buildApp(httpBackends("http://dispatch", "http://payments"));
    const res = await app.yoga.fetch("http://gateway/graphql", {
      method: "POST",
      headers: { "content-type": "application/json", "x-session-id": "s-h", "x-app-version": "1.6.0" },
      body: JSON.stringify({ query: `{ places(city: "sf") { id name } }` }),
    });
    const body = (await res.json()) as { data?: { places: { id: string | null; name: string }[] } };
    expect(body.data?.places).toEqual([
      { id: "sf-ferry", name: "Ferry Building" },
      { id: "sf-sfo", name: "SFO Airport" },
    ]);
  });
});
