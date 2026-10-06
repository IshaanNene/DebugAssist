// Hidden test for BUG-017 (never committed to the target repo). Copied to gateway/test/ at eval time.
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

async function preflight(env: string, origin: string): Promise<string | null> {
  vi.stubEnv("CORS_ORIGINS", env);
  vi.resetModules();
  const { buildApp } = await import("../src/app.js");
  const app = buildApp();
  const res = await app.yoga.fetch("http://gateway/graphql", {
    method: "OPTIONS",
    headers: { origin, "access-control-request-method": "POST", "access-control-request-headers": "content-type" },
  });
  return res.headers.get("access-control-allow-origin");
}

describe("CORS origins from the environment (hidden)", () => {
  it.each([
    ["http://localhost:8080,http://localhost:8081", "http://localhost:8081"],
    ["http://localhost:8080,http://localhost:8081", "http://localhost:8080"],
    ["http://localhost:8080, http://localhost:8081", "http://localhost:8081"],
  ])("CORS_ORIGINS=%s allows %s", async (env, origin) => {
    expect(await preflight(env, origin)).toBe(origin);
  });

  it("does not allow an origin that is not listed", async () => {
    expect(await preflight("http://localhost:8080", "http://evil.example")).not.toBe("http://evil.example");
  });
});
