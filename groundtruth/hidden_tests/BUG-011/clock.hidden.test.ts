// Hidden test for BUG-011 (never committed to the target repo). Copied to test/ at eval time.
import { describe, expect, it } from "vitest";
import { pickupClock } from "../src/screens/RideScreen";

const NOW = Date.UTC(2026, 9, 5, 10, 0, 0); // 10:00 UTC

describe("pickup clock for every city (hidden)", () => {
  it("formats Bengaluru times in India Standard Time (UTC+5:30)", () => {
    const expected = new Date(NOW + 600_000).toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
      timeZone: "Asia/Kolkata",
    });
    expect(pickupClock(600, "blr", NOW)).toBe(expected);
  });
  it("never throws, even for a city without a known time zone", () => {
    expect(() => pickupClock(60, "paris", NOW)).not.toThrow();
  });
});
