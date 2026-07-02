import { describe, it, expect } from "vitest";

import { groupRuns } from "@/lib/runsGrouping";
import type { RunSummary } from "@/types";

function run(id: string, overrides: Partial<RunSummary> = {}): RunSummary {
  return {
    id,
    kind: "synth",
    status: "passed",
    createdAt: "2026-07-02T10:00:00Z",
    top: "top",
    pinned: false,
    ...overrides,
  };
}

describe("groupRuns", () => {
  it("returns empty for no runs", () => {
    expect(groupRuns([])).toEqual([]);
  });

  it("runs without parents are all roots, ordered newest-first", () => {
    const a = run("synth_0001", { createdAt: "2026-07-02T09:00:00Z" });
    const b = run("synth_0002", { createdAt: "2026-07-02T11:00:00Z" });
    const c = run("sim_0001", { kind: "sim", createdAt: "2026-07-02T10:00:00Z" });
    const groups = groupRuns([a, b, c]);
    expect(groups.map((g) => g.root.id)).toEqual(["synth_0002", "sim_0001", "synth_0001"]);
    expect(groups.every((g) => g.children.length === 0)).toBe(true);
  });

  it("children nest under their root, oldest-first", () => {
    const root = run("synth_0001", { createdAt: "2026-07-02T09:00:00Z" });
    const retryNew = run("synth_0003", {
      parentRunId: "synth_0001",
      createdAt: "2026-07-02T11:00:00Z",
    });
    const retryOld = run("synth_0002", {
      parentRunId: "synth_0001",
      createdAt: "2026-07-02T10:00:00Z",
    });
    const groups = groupRuns([retryNew, retryOld, root]);
    expect(groups).toHaveLength(1);
    expect(groups[0].root.id).toBe("synth_0001");
    expect(groups[0].children.map((c) => c.id)).toEqual(["synth_0002", "synth_0003"]);
  });

  it("orphan parent → the run is treated as a root", () => {
    const orphan = run("synth_0005", {
      parentRunId: "synth_gone",
      createdAt: "2026-07-02T12:00:00Z",
    });
    const other = run("synth_0001", { createdAt: "2026-07-02T09:00:00Z" });
    const groups = groupRuns([orphan, other]);
    expect(groups.map((g) => g.root.id)).toEqual(["synth_0005", "synth_0001"]);
    expect(groups[0].children).toEqual([]);
  });

  it("retry chains (grandchildren) flatten under the chain's root", () => {
    const a = run("synth_0001", { createdAt: "2026-07-02T09:00:00Z" });
    const b = run("synth_0002", { parentRunId: "synth_0001", createdAt: "2026-07-02T10:00:00Z" });
    const c = run("synth_0003", { parentRunId: "synth_0002", createdAt: "2026-07-02T11:00:00Z" });
    const groups = groupRuns([c, b, a]);
    expect(groups).toHaveLength(1);
    expect(groups[0].root.id).toBe("synth_0001");
    expect(groups[0].children.map((x) => x.id)).toEqual(["synth_0002", "synth_0003"]);
  });

  it("a chain whose root is an orphan groups under the orphan", () => {
    // parent of the chain head is missing → head becomes the root.
    const head = run("synth_0002", {
      parentRunId: "synth_missing",
      createdAt: "2026-07-02T10:00:00Z",
    });
    const child = run("synth_0003", {
      parentRunId: "synth_0002",
      createdAt: "2026-07-02T11:00:00Z",
    });
    const groups = groupRuns([child, head]);
    expect(groups).toHaveLength(1);
    expect(groups[0].root.id).toBe("synth_0002");
    expect(groups[0].children.map((x) => x.id)).toEqual(["synth_0003"]);
  });

  it("null createdAt sorts roots last and children first (treated as epoch 0)", () => {
    const dated = run("synth_0002", { createdAt: "2026-07-02T10:00:00Z" });
    const undated = run("synth_0001", { createdAt: null });
    const groups = groupRuns([undated, dated]);
    expect(groups.map((g) => g.root.id)).toEqual(["synth_0002", "synth_0001"]);
  });

  it("is cycle-safe (malformed parent loops still surface every run)", () => {
    const a = run("synth_0001", { parentRunId: "synth_0002" });
    const b = run("synth_0002", { parentRunId: "synth_0001" });
    const groups = groupRuns([a, b]);
    const ids = groups.flatMap((g) => [g.root.id, ...g.children.map((c) => c.id)]);
    expect(ids.sort()).toEqual(["synth_0001", "synth_0002"]);
  });
});
