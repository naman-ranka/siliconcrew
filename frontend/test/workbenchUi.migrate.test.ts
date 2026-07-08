import { describe, it, expect } from "vitest";
import { migrateWorkbenchUi } from "@/lib/workbenchUiStore";

describe("workbench UI persist migration v1 → v2 (#7 stale tab keys)", () => {
  it("remaps a stale code:*.vcd tab key to wavefile: (openTabs + activeTab)", () => {
    const v1 = {
      perSession: {
        s1: {
          openTabs: ["code:rtl/counter.v", "code:sim_runs/sim_0001/dump.vcd"],
          activeTab: "code:sim_runs/sim_0001/dump.vcd",
        },
      },
      lastSessionId: "s1",
    };
    const out = migrateWorkbenchUi(v1, 1) as typeof v1;
    expect(out.perSession.s1.openTabs).toEqual([
      "code:rtl/counter.v",
      "wavefile:sim_runs/sim_0001/dump.vcd",
    ]);
    expect(out.perSession.s1.activeTab).toBe("wavefile:sim_runs/sim_0001/dump.vcd");
    // untouched top-level fields survive
    expect(out.lastSessionId).toBe("s1");
  });

  it("dedups when the remapped wavefile: key is already open (no double tab)", () => {
    const v1 = {
      perSession: {
        s1: {
          openTabs: ["wavefile:a/x.vcd", "code:a/x.vcd"],
          activeTab: "code:a/x.vcd",
        },
      },
    };
    const out = migrateWorkbenchUi(v1, 1) as typeof v1;
    expect(out.perSession.s1.openTabs).toEqual(["wavefile:a/x.vcd"]);
  });

  it("leaves non-.vcd code keys and already-migrated (v2) state alone", () => {
    const state = { perSession: { s1: { openTabs: ["code:rtl/top.v"], activeTab: "code:rtl/top.v" } } };
    expect(migrateWorkbenchUi(state, 1)).toEqual(state);
    // v2+ is a no-op passthrough
    expect(migrateWorkbenchUi(state, 2)).toBe(state);
  });

  it("never throws on malformed persisted state", () => {
    expect(migrateWorkbenchUi(null, 1)).toBeNull();
    expect(migrateWorkbenchUi({ perSession: { s1: null } } as any, 1)).toEqual({ perSession: { s1: null } });
    expect(migrateWorkbenchUi({ perSession: { s1: { openTabs: "nope" } } } as any, 1)).toEqual({
      perSession: { s1: { openTabs: "nope" } },
    });
  });
});
