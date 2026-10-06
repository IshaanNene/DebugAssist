// Hidden test for BUG-009 (never committed to the target repo). Copied to test/ at eval time.
import { describe, expect, it } from "vitest";
import { nearestFirst } from "../src/screens/Search";

const tokyo = [
  { id: "tyo-hnd", name: "Haneda Airport", lat: 35.5494, lng: 139.7798 },
  { id: "tyo-shibuya", name: "Shibuya Crossing", lat: 35.6595, lng: 139.7005 },
  { id: "tyo-shinjuku", name: "Shinjuku Station", lat: 35.6896, lng: 139.7006 },
];

describe("place ordering for every city (hidden)", () => {
  it("orders Tokyo places without throwing and keeps all of them", () => {
    const out = nearestFirst("tokyo", tokyo);
    expect(out.map((p) => p.id).sort()).toEqual(tokyo.map((p) => p.id).sort());
    expect(out[out.length - 1]?.id).toBe("tyo-hnd"); // the airport is furthest from the centre
  });

  it("keeps the server's order for a city it does not know", () => {
    expect(() => nearestFirst("paris", tokyo)).not.toThrow();
    expect(nearestFirst("paris", tokyo)).toHaveLength(3);
  });
});
