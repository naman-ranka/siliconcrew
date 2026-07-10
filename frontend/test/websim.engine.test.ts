// @vitest-environment node
// The real digitaljs engine loads jointjs, whose browser dist needs real SVG
// support jsdom lacks — these tests run in node (the engine itself is
// DOM-free; browsers get e2e coverage via playwright).
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";
import { createWebsimSession, parseWebsimPayload } from "@/lib/websim";

const FIXTURES = path.resolve(__dirname, "fixtures/websim");
const payloadText = readFileSync(path.join(FIXTURES, "counter.websim.json"), "utf8");

describe("createWebsimSession — REAL engine on the counter netlist", () => {
  it("simulates the synthesized counter: reset, count, hold", async () => {
    const payload = parseWebsimPayload(payloadText)!;
    const s = await createWebsimSession(payload);

    expect(s.hasClock).toBe(true);
    expect(s.ports.find((p) => p.name === "count")?.bits).toBe(4);

    // inputs start low → rst_n=0 holds the counter in reset
    expect(s.readOutputs().count).toBe(0);

    s.setInput("rst_n", 1);
    s.setInput("en", 1);
    for (let i = 0; i < 5; i++) s.tickCycle();
    expect(s.readOutputs().count).toBe(5);
    expect(s.cycle).toBe(5);

    // en=0 → holds
    s.setInput("en", 0);
    s.tickCycle();
    expect(s.readOutputs().count).toBe(5);

    // async reset mid-run
    s.setInput("rst_n", 0);
    s.tickCycle();
    expect(s.readOutputs().count).toBe(0);

    // 4-bit wrap
    s.setInput("rst_n", 1);
    s.setInput("en", 1);
    for (let i = 0; i < 17; i++) s.tickCycle();
    expect(s.readOutputs().count).toBe(1);

    s.dispose();
  });

  it("ignores unknown input names instead of crashing agent dashboards", async () => {
    const payload = parseWebsimPayload(payloadText)!;
    const s = await createWebsimSession(payload);
    expect(() => s.setInput("no_such_port", 1)).not.toThrow();
    s.dispose();
  });
});
