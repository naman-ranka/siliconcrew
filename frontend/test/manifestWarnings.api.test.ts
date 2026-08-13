import { describe, it, expect, afterEach, vi } from "vitest";

// sc#66 (remaining frontend hop): the backend attaches `manifestWarnings`
// (duplicate-module collision advisories) to /simulate and /synthesize replies.
// The API layer previously typed simulate as { ok, run } and returned only the
// run — silently dropping the warnings before any component could render them.
// These tests pin the type-through: the field survives the API layer intact.

import { workbenchApi } from "@/lib/api";
import type { RunSummary } from "@/types";

const SIM_RUN: RunSummary = {
  id: "sim_0001",
  kind: "sim",
  status: "passed",
  createdAt: null,
  top: "gcn_tb",
  pinned: false,
};

const WARNING =
  "module 'GCN' is declared by both given/gcn.sv and solution/gcn.sv — " +
  "ignore one (manifest `ignore` glob) or change its role.";

function stubFetch(body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    })
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("workbenchApi.simulate carries manifestWarnings through", () => {
  it("returns { run, manifestWarnings } from the backend envelope", async () => {
    stubFetch({ ok: true, run: SIM_RUN, manifestWarnings: [WARNING] });
    const res = await workbenchApi.simulate("s1", { mode: "rtl" });
    expect(res.run).toEqual(SIM_RUN);
    expect(res.manifestWarnings).toEqual([WARNING]);
  });

  it("normalizes an absent field to [] (older backends)", async () => {
    stubFetch({ ok: true, run: SIM_RUN });
    const res = await workbenchApi.simulate("s1");
    expect(res.run).toEqual(SIM_RUN);
    expect(res.manifestWarnings).toEqual([]);
  });
});

describe("workbenchApi.synthesize carries manifestWarnings through", () => {
  it("keeps the field on the dispatch envelope", async () => {
    stubFetch({ ok: true, runId: "synth_0001", pollAfterSec: 5, manifestWarnings: [WARNING] });
    const res = await workbenchApi.synthesize("s1", { maxStage: "synth" });
    expect(res.runId).toBe("synth_0001");
    expect(res.manifestWarnings).toEqual([WARNING]);
  });
});
