import { describe, it, expect, beforeEach, vi } from "vitest";

// F4/F5: loadWorkbench hydrates ONCE via the snapshot, is single-flight (so the
// double-open + the active-run poll never double-fetch), and falls back to the
// granular loaders when the snapshot is unavailable.
vi.mock("@/lib/api", () => ({
  projectsApi: {},
  sessionsApi: {},
  chatApi: {},
  workspaceApi: {
    listFiles: vi.fn().mockResolvedValue([]),
    listWaveforms: vi.fn().mockResolvedValue([]),
    listLayouts: vi.fn().mockResolvedValue({ layouts: [], missing_binaries: [] }),
    listSchematics: vi.fn().mockResolvedValue([]),
    listSynthesisRuns: vi.fn().mockResolvedValue([]),
  },
  workbenchApi: {
    getWorkbench: vi.fn(),
    getManifest: vi.fn().mockResolvedValue(null),
    listRuns: vi.fn().mockResolvedValue([]),
  },
}));

import { useStore } from "@/lib/store";
import { workbenchApi, workspaceApi } from "@/lib/api";

const SESSION = { id: "s1", name: "s1", model_name: "m", project_id: null, created_at: null, updated_at: null, total_tokens: 0, total_cost: 0 };

const SNAPSHOT = {
  ok: true as const,
  manifest: { sessionId: "s1", files: [{ name: "counter.v", role: "rtl", path: "counter.v" }], synthTop: "counter", simTop: "", clockPeriodNs: 10, platform: "sky130hd" },
  runs: [{ id: "synth_0001", kind: "synth", status: "passed", createdAt: "2024-01-01", top: "counter", pinned: false }],
  files: [{ name: "counter.v", path: "counter.v", type: "verilog", size: 10, modified: "2024-01-01T00:00:00", role: "rtl" }],
  spec: { filename: "design_spec.yaml", content: "top: counter", parsed: { top: "counter" } },
  code: [{ filename: "counter.v", content: "module counter; endmodule", language: "verilog" }],
  report: null,
  synthesisRuns: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  useStore.setState({ currentSession: SESSION as any, files: [], runs: [], codeFiles: [], manifest: null });
});

describe("loadWorkbench: one-hydration snapshot", () => {
  it("uses the snapshot endpoint and populates state in one call", async () => {
    (workbenchApi.getWorkbench as any).mockResolvedValue(SNAPSHOT);

    await useStore.getState().loadWorkbench();

    expect(workbenchApi.getWorkbench).toHaveBeenCalledTimes(1);
    expect(workbenchApi.getWorkbench).toHaveBeenCalledWith("s1");
    const s = useStore.getState();
    expect(s.manifest?.synthTop).toBe("counter");
    expect(s.runs[0].id).toBe("synth_0001");
    expect(s.files[0].name).toBe("counter.v");
    expect(s.codeFiles[0].filename).toBe("counter.v");
    expect(s.selectedCodeFile).toBe("counter.v");
    expect(s.spec?.filename).toBe("design_spec.yaml");
    // No granular fan-out when the snapshot succeeds.
    expect(workbenchApi.getManifest).not.toHaveBeenCalled();
    expect(workspaceApi.listFiles).not.toHaveBeenCalled();
  });

  it("is single-flight: concurrent callers share ONE snapshot fetch", async () => {
    let resolve!: (v: unknown) => void;
    (workbenchApi.getWorkbench as any).mockReturnValue(new Promise((r) => (resolve = r)));

    const a = useStore.getState().loadWorkbench();
    const b = useStore.getState().loadWorkbench(); // the "double open" / poll overlap
    resolve(SNAPSHOT);
    await Promise.all([a, b]);

    expect(workbenchApi.getWorkbench).toHaveBeenCalledTimes(1);
  });

  it("falls back to the granular loaders when the snapshot errors", async () => {
    (workbenchApi.getWorkbench as any).mockRejectedValue(new Error("no snapshot endpoint"));

    await useStore.getState().loadWorkbench();

    // Fallback fan-out ran (older backend path stays correct).
    expect(workbenchApi.getManifest).toHaveBeenCalledWith("s1");
    expect(workbenchApi.listRuns).toHaveBeenCalled();
    expect(workspaceApi.listFiles).toHaveBeenCalled();
  });
});

describe("loadRuns: single-flight (F5 poll dedup)", () => {
  it("concurrent poll + mount share ONE listRuns fetch", async () => {
    let resolve!: (v: unknown) => void;
    (workbenchApi.listRuns as any).mockReturnValue(new Promise((r) => (resolve = r)));

    const a = useStore.getState().loadRuns();
    const b = useStore.getState().loadRuns(); // the second polling loop
    resolve([]);
    await Promise.all([a, b]);

    expect(workbenchApi.listRuns).toHaveBeenCalledTimes(1);
  });
});

describe("refreshWorkspace: single-flight", () => {
  it("concurrent refreshes share ONE listFiles fetch", async () => {
    let resolve!: (v: unknown) => void;
    (workspaceApi.listFiles as any).mockReturnValue(new Promise((r) => (resolve = r)));

    const a = useStore.getState().refreshWorkspace();
    const b = useStore.getState().refreshWorkspace();
    resolve([]);
    await Promise.all([a, b]);

    expect(workspaceApi.listFiles).toHaveBeenCalledTimes(1);
  });
});
