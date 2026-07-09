import { describe, it, expect } from "vitest";

import {
  dirPrefixesForPath,
  flattenTree,
  runIdForDirEntry,
  moduleNameForFile,
  isSynthTopFile,
  isSimTopFile,
  validateNewFilePath,
  type DirSliceLike,
} from "@/lib/fileTree";
import type { DesignManifest, DirEntry } from "@/types";

const dir = (path: string): DirEntry => ({
  name: path.split("/").pop() || path,
  path,
  kind: "dir",
});
const file = (path: string): DirEntry => ({
  name: path.split("/").pop() || path,
  path,
  kind: "file",
});

const ready = (entries: DirEntry[]): DirSliceLike => ({ status: "ready", entries, error: null });

describe("flattenTree", () => {
  const root = ready([dir("sim_runs"), file("counter.v"), file("tb_counter.v")]);

  it("root only, nothing expanded — order preserved, all collapsed", () => {
    const out = flattenTree({ "": root }, []);
    expect(out.map((n) => n.entry.path)).toEqual(["sim_runs", "counter.v", "tb_counter.v"]);
    expect(out.every((n) => n.depth === 0 && !n.expanded && !n.loading)).toBe(true);
  });

  it("empty cache (no root slice) flattens to nothing", () => {
    expect(flattenTree({}, [])).toEqual([]);
    expect(flattenTree({}, ["sim_runs"])).toEqual([]);
  });

  it("nested expand recurses with depth+1, children inline after their dir", () => {
    const cache = {
      "": root,
      sim_runs: ready([dir("sim_runs/sim_0001")]),
      "sim_runs/sim_0001": ready([file("sim_runs/sim_0001/dump.vcd")]),
    };
    const out = flattenTree(cache, ["sim_runs", "sim_runs/sim_0001"]);
    expect(out.map((n) => [n.entry.path, n.depth])).toEqual([
      ["sim_runs", 0],
      ["sim_runs/sim_0001", 1],
      ["sim_runs/sim_0001/dump.vcd", 2],
      ["counter.v", 0],
      ["tb_counter.v", 0],
    ]);
    expect(out[0].expanded).toBe(true);
    expect(out[1].expanded).toBe(true);
    expect(out[2].expanded).toBe(false); // files are never "expanded"
  });

  it("expanded but uncached dir carries a loading marker and no children", () => {
    const out = flattenTree({ "": root }, ["sim_runs"]);
    expect(out).toHaveLength(3);
    expect(out[0]).toMatchObject({ expanded: true, loading: true, depth: 0 });
    expect(out[1].entry.path).toBe("counter.v"); // siblings still follow
  });

  it('expanded dir with a "loading" empty slice is also a loading marker', () => {
    const cache = {
      "": root,
      sim_runs: { status: "loading", entries: [], error: null } as DirSliceLike,
    };
    const out = flattenTree(cache, ["sim_runs"]);
    expect(out[0]).toMatchObject({ expanded: true, loading: true });
    expect(out.map((n) => n.entry.path)).toEqual(["sim_runs", "counter.v", "tb_counter.v"]);
  });

  it("revalidating slice keeps stale children visible (SWR rule), not loading", () => {
    const cache = {
      "": root,
      sim_runs: {
        status: "revalidating",
        entries: [dir("sim_runs/sim_0001")],
        error: null,
      } as DirSliceLike,
    };
    const out = flattenTree(cache, ["sim_runs"]);
    expect(out[0]).toMatchObject({ expanded: true, loading: false });
    expect(out[1].entry.path).toBe("sim_runs/sim_0001");
    expect(out[1].depth).toBe(1);
  });

  it("expanded READY-but-empty dir is not loading and yields no children", () => {
    const cache = { "": root, sim_runs: ready([]) };
    const out = flattenTree(cache, ["sim_runs"]);
    expect(out[0]).toMatchObject({ expanded: true, loading: false });
    expect(out).toHaveLength(3);
  });

  it("ordering is exactly the per-dir server order, never re-sorted", () => {
    const cache = {
      "": ready([file("z.v"), dir("a_dir"), file("b.v")]),
      a_dir: ready([file("a_dir/y.md"), file("a_dir/a.md")]),
    };
    const out = flattenTree(cache, ["a_dir"]);
    expect(out.map((n) => n.entry.path)).toEqual(["z.v", "a_dir", "a_dir/y.md", "a_dir/a.md", "b.v"]);
  });
});

describe("runIdForDirEntry", () => {
  it("matches run dirs directly under sim_runs / synth_runs", () => {
    expect(runIdForDirEntry(dir("sim_runs/sim_0001"))).toBe("sim_0001");
    expect(runIdForDirEntry(dir("synth_runs/synth_0042"))).toBe("synth_0042");
  });

  it("rejects files, wrong parents, mismatched kinds, and nested paths", () => {
    expect(runIdForDirEntry(file("sim_runs/sim_0001"))).toBeNull();
    expect(runIdForDirEntry(dir("sim_0001"))).toBeNull(); // not under sim_runs
    expect(runIdForDirEntry(dir("sim_runs/synth_0001"))).toBeNull(); // kind mismatch
    expect(runIdForDirEntry(dir("synth_runs/sim_0001"))).toBeNull();
    expect(runIdForDirEntry(dir("sim_runs/sim_0001/artifacts"))).toBeNull();
    expect(runIdForDirEntry(dir("other/sim_runs/sim_0001"))).toBeNull();
    expect(runIdForDirEntry(dir("sim_runs/sim_abc"))).toBeNull();
  });
});

describe("top-module heuristics", () => {
  const manifest: DesignManifest = {
    sessionId: "s1",
    files: [
      { name: "counter.v", role: "rtl", path: "counter.v" },
      { name: "tb_counter.sv", role: "tb", path: "tb_counter.sv" },
      { name: "counter.sdc", role: "sdc", path: "counter.sdc" },
    ],
    synthTop: "counter",
    simTop: "tb_counter",
    clockPeriodNs: 10,
    platform: "sky130hd",
  };

  it("strips .v/.sv for the module-name heuristic", () => {
    expect(moduleNameForFile("counter.v")).toBe("counter");
    expect(moduleNameForFile("tb_counter.sv")).toBe("tb_counter");
    expect(moduleNameForFile("notes.md")).toBe("notes.md");
  });

  it("isSynthTopFile requires rtl role + module match", () => {
    expect(isSynthTopFile("counter.v", manifest)).toBe(true);
    expect(isSynthTopFile("tb_counter.sv", manifest)).toBe(false);
    expect(isSynthTopFile("counter.sdc", manifest)).toBe(false); // not rtl, name mismatch anyway
    expect(isSynthTopFile("counter.v", null)).toBe(false);
  });

  it("isSimTopFile requires tb role + module match", () => {
    expect(isSimTopFile("tb_counter.sv", manifest)).toBe(true);
    expect(isSimTopFile("counter.v", manifest)).toBe(false);
    expect(isSimTopFile("tb_counter.sv", null)).toBe(false);
  });
});

describe("validateNewFilePath", () => {
  it("accepts plain and nested workspace-relative paths", () => {
    expect(validateNewFilePath("alu.v")).toBeNull();
    expect(validateNewFilePath("rtl/core/alu.v")).toBeNull();
    expect(validateNewFilePath("  spec.md  ")).toBeNull(); // trimmed
  });

  it("rejects empty input", () => {
    expect(validateNewFilePath("")).not.toBeNull();
    expect(validateNewFilePath("   ")).not.toBeNull();
  });

  it("rejects a leading slash", () => {
    expect(validateNewFilePath("/etc/passwd")).not.toBeNull();
  });

  it("rejects '..' / '.' / empty segments", () => {
    expect(validateNewFilePath("../escape.v")).not.toBeNull();
    expect(validateNewFilePath("rtl/../escape.v")).not.toBeNull();
    expect(validateNewFilePath("rtl/./alu.v")).not.toBeNull();
    expect(validateNewFilePath("rtl//alu.v")).not.toBeNull();
    expect(validateNewFilePath("rtl/")).not.toBeNull(); // trailing slash = empty segment
  });
});

describe("dirPrefixesForPath", () => {
  it("root file → just the root", () => {
    expect(dirPrefixesForPath("alu.v")).toEqual([""]);
  });
  it("nested file → root plus every ancestor dir", () => {
    expect(dirPrefixesForPath("rtl/core/alu.v")).toEqual(["", "rtl", "rtl/core"]);
  });
});
