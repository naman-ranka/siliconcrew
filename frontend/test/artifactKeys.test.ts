import { describe, it, expect } from "vitest";

import { makeArtifactKey, parseArtifactKey } from "@/lib/artifactKeys";

describe("artifactKeys: make/parse round-trip", () => {
  it("round-trips every ref-carrying kind", () => {
    const cases = [
      ["code", "counter.v"],
      ["wave", "sim_0001"],
      ["report", "synth_0002"],
      ["layout", "synth_0002"],
      ["schematic", "cpu_top.svg"],
    ] as const;
    for (const [kind, ref] of cases) {
      const key = makeArtifactKey(kind, ref);
      expect(key).toBe(`${kind}:${ref}`);
      expect(parseArtifactKey(key)).toEqual({ kind, ref });
    }
  });

  it("spec is a singleton key with no ref", () => {
    expect(makeArtifactKey("spec")).toBe("spec");
    expect(parseArtifactKey("spec")).toEqual({ kind: "spec", ref: null });
  });

  it("code paths with dots and slashes survive (split only on the FIRST colon)", () => {
    const path = "sim_runs/sim_0001/dump.tb.v";
    const key = makeArtifactKey("code", path);
    expect(key).toBe("code:sim_runs/sim_0001/dump.tb.v");
    expect(parseArtifactKey(key)).toEqual({ kind: "code", ref: path });
  });

  it("a ref containing a colon stays intact past the first split", () => {
    const parsed = parseArtifactKey("schematic:weird:name.svg");
    expect(parsed).toEqual({ kind: "schematic", ref: "weird:name.svg" });
  });

  it("rejects unknown kinds and malformed keys", () => {
    expect(parseArtifactKey("bogus:x")).toBeNull();
    expect(parseArtifactKey(":noprefix")).toBeNull();
    expect(parseArtifactKey("justastring")).toBeNull();
    expect(parseArtifactKey("")).toBeNull();
  });
});
