// Hidden test for BUG-008 (never committed to the target repo). Copied to test/ at eval time.
import { describe, expect, it } from "vitest";
import { localeDirection } from "../src/i18n";

describe("locales without a region subtag", () => {
  it.each([
    ["ar", "rtl"],
    ["he", "rtl"],
    ["fa", "rtl"],
    ["en", "ltr"],
    ["zh-Hant-TW", "ltr"],
  ])("%s does not throw and is %s", (locale, dir) => {
    const out = localeDirection(locale);
    expect(out.dir).toBe(dir);
    expect(out.lang.toLowerCase().startsWith(locale.split("-")[0]!)).toBe(true);
  });
});
