import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("html-to-image", () => ({ toPng: vi.fn().mockRejectedValue(new Error("no canvas in jsdom")) }));

import * as BugDrop from "../src/index";
import { redactText } from "../src/redact";

describe("redactText", () => {
  it("removes PII but keeps ordinary text", () => {
    expect(redactText("mail jo@example.com or call +1 415-555-0134, card 4242 4242 4242 4242")).toBe(
      "mail [email] or call [phone], card [card]",
    );
    expect(redactText("ride took 1234 ms at 30%")).toBe("ride took 1234 ms at 30%");
    expect(redactText("Authorization: Bearer abcdefghijklmnop")).toBe("Authorization: Bearer [token]");
  });
});

describe("BugDrop", () => {
  let visibility: DocumentVisibilityState = "visible";
  beforeEach(() => {
    BugDrop._reset();
    visibility = "visible";
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        String(url).includes("/graphql")
          ? new Response(JSON.stringify({ errors: [{ message: "x", extensions: { code: "NO_DRIVERS" } }] }))
          : new Response("{}", { status: 200 }),
      ),
    );
    BugDrop.init({
      endpoint: "http://bugdrop",
      app: "miniride-client",
      version: "1.6.0",
      sessionId: "s1",
      getUiState: () => ({ route: location.pathname, visibility, activeRideId: "r1" }),
      getFlags: () => ({ notif_router_v2: false }),
      getCity: () => "sf",
      getDevice: () => ({ os: "Android 15", browser: "Chrome 141" }),
    });
  });

  it("captures network and GraphQL operations without bodies", async () => {
    await fetch("http://gw/graphql", { method: "POST", body: JSON.stringify({ operationName: "RequestRide", variables: { secret: "x" } }) });
    await fetch("http://gw/rides/0f8fad5b-d9cb-469f-a165-70867728950e/eta");
    await new Promise((r) => setTimeout(r, 0));
    const report = BugDrop.buildReport("My phone is heating up. jo@example.com") as any;
    expect(report.logs.network.map((e: any) => e.url)).toEqual(["http://gw/graphql", "http://gw/rides/:id/eta"]);
    expect(report.logs.network[0]).not.toHaveProperty("body");
    expect(report.logs.graphql[0]).toMatchObject({ operationName: "RequestRide", errors: ["NO_DRIVERS"] });
    expect(report.description).toBe("My phone is heating up. [email]");
    expect(report.flags).toEqual({ notif_router_v2: false });
  });

  it("snapshots UI state on visibility changes", () => {
    visibility = "hidden";
    document.dispatchEvent(new Event("visibilitychange"));
    BugDrop.recordAnalytics({ name: "eta_background_tick", ts: Date.now() });
    const report = BugDrop.buildReport("x") as any;
    const states = report.logs.ui_state.map((s: any) => s.visibility);
    expect(states).toContain("hidden");
    expect(report.logs.ui_state.at(-1)).toMatchObject({ reason: "report", activeRideId: "r1" });
    expect(report.logs.analytics[0].name).toBe("eta_background_tick");
  });

  it("uploads multipart with attachments", async () => {
    const transport = vi.fn(async () => new Response(JSON.stringify({ id: "BD-1001" }), { status: 201 }));
    const img = new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], "battery.png", { type: "image/png" });
    const out = await BugDrop.submit({ description: "battery", attachments: [img] }, transport as unknown as typeof fetch);
    expect(out.id).toBe("BD-1001");
    const [url, init] = transport.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://bugdrop/v1/reports");
    const form = init.body as FormData;
    expect(JSON.parse(String(form.get("report"))).app).toBe("miniride-client");
    expect((form.getAll("attachments")[0] as File).name).toBe("battery.png");
  });
});
