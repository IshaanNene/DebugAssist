// Hidden test for BUG-010 (never committed to the target repo). Copied to test/ at eval time.
import { describe, expect, it } from "vitest";
import { formatMoney } from "../src/screens/RequestRide";

const digits = (s: string) => Number(s.replace(/[^\d.]/g, ""));

describe("fare formatting in minor units (hidden)", () => {
  it("formats yen amounts as whole yen (JPY has no minor unit)", () => {
    expect(digits(formatMoney(2345, "JPY"))).toBe(2345);
  });
  it("still formats cents for USD and paise for INR", () => {
    expect(digits(formatMoney(1234, "USD"))).toBe(12.34);
    expect(digits(formatMoney(90000, "INR"))).toBe(900);
  });
});
