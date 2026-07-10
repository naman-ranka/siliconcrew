import { describe, it, expect, beforeAll } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";
import { webcrypto } from "node:crypto";
import {
  BRIDGE_SOURCE,
  checkProvenance,
  composeSrcdoc,
  parseSimMeta,
  parseWebsimPayload,
  sha256Hex,
  WEBSIM_FORMAT,
} from "@/lib/websim";

// jsdom's window.crypto has no subtle — hashing uses node's webcrypto.
beforeAll(() => {
  if (!globalThis.crypto?.subtle) {
    Object.defineProperty(globalThis, "crypto", { value: webcrypto, configurable: true });
  }
});

const FIXTURES = path.resolve(__dirname, "fixtures/websim");
const payloadText = readFileSync(path.join(FIXTURES, "counter.websim.json"), "utf8");
const counterSource = readFileSync(path.join(FIXTURES, "counter.v"));

const toArrayBuffer = (buf: Buffer): ArrayBuffer =>
  buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) as ArrayBuffer;

describe("parseWebsimPayload", () => {
  it("accepts the v1 fixture and rejects shapeless/foreign JSON", () => {
    const p = parseWebsimPayload(payloadText);
    expect(p?.format).toBe(WEBSIM_FORMAT);
    expect(p?.top).toBe("counter");
    expect(p?.ports.map((x) => x.name)).toContain("count");

    expect(parseWebsimPayload("not json")).toBeNull();
    expect(parseWebsimPayload("{}")).toBeNull();
    expect(parseWebsimPayload(JSON.stringify({ format: "something-else" }))).toBeNull();
  });
});

describe("parseSimMeta", () => {
  it("finds the declared netlist and treats its absence as a mockup", () => {
    expect(
      parseSimMeta('<html><head><meta name="siliconcrew-sim" content="counter.websim.json"></head></html>')
    ).toBe("counter.websim.json");
    expect(parseSimMeta("<html><body><h1>hi</h1></body></html>")).toBeNull();
    expect(parseSimMeta('<meta name="siliconcrew-sim" content="  ">')).toBeNull();
  });
});

describe("composeSrcdoc", () => {
  it("injects the bridge as the FIRST head script, preserving agent content", () => {
    const out = composeSrcdoc("<html><head><script>window.agent=1</script></head><body><b>ui</b></body></html>");
    expect(out.startsWith("<!doctype html>")).toBe(true);
    expect(out).toContain("window.simBridge");
    expect(out).toContain("<b>ui</b>");
    // bridge before the agent's own script — the API must exist when agent code runs
    expect(out.indexOf("window.simBridge")).toBeLessThan(out.indexOf("window.agent=1"));
  });

  it("normalizes a bare fragment into a full document", () => {
    const out = composeSrcdoc("<div>just a fragment</div>");
    expect(out).toContain("window.simBridge");
    expect(out).toContain("just a fragment");
  });
});

describe("bridge source", () => {
  it("only talks postMessage — no engine access, no network, no parent DOM", () => {
    expect(BRIDGE_SOURCE).toContain("postMessage");
    for (const forbidden of ["fetch(", "XMLHttpRequest", "parent.document", "localStorage"]) {
      expect(BRIDGE_SOURCE).not.toContain(forbidden);
    }
  });
});

describe("checkProvenance (content hashes, never mtimes)", () => {
  const payload = parseWebsimPayload(payloadText)!;

  it("fresh when the current bytes hash to the recorded value", async () => {
    const res = await checkProvenance(payload, async () => toArrayBuffer(counterSource));
    expect(res).toBe("fresh");
  });

  it("stale when the source changed or disappeared", async () => {
    const edited = Buffer.concat([counterSource, Buffer.from("\n// edited\n")]);
    expect(await checkProvenance(payload, async () => toArrayBuffer(edited))).toBe("stale");
    expect(
      await checkProvenance(payload, async () => {
        throw new Error("404");
      })
    ).toBe("stale");
  });

  it("sha256Hex matches the backend's hashing of the same bytes", async () => {
    // recorded value in the fixture was produced by python hashlib on these bytes
    const recorded = payload.sources["counter.v"];
    expect(await sha256Hex(toArrayBuffer(counterSource))).toBe(recorded);
  });
});
