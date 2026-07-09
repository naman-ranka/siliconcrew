import { describe, it, expect, beforeEach, vi } from "vitest";

// Mock the API layer so the store tests run with no backend (Tier 1, jsdom).
vi.mock("@/lib/api", () => {
  return {
    projectsApi: { list: vi.fn().mockResolvedValue([]) },
    sessionsApi: { list: vi.fn().mockResolvedValue([]) },
    chatApi: {},
    workspaceApi: {
      listFiles: vi.fn().mockResolvedValue([]),
      listWaveforms: vi.fn().mockResolvedValue([]),
      listLayouts: vi.fn().mockResolvedValue({ layouts: [], missing_binaries: [] }),
      listSchematics: vi.fn().mockResolvedValue([]),
      listSynthesisRuns: vi.fn().mockResolvedValue([]),
      getWaveform: vi.fn().mockResolvedValue({ filename: "x.vcd", endtime: 240, signals: [] }),
      getReport: vi.fn().mockResolvedValue({ filename: "r.md", content: "# r", run_id: "synth_0001" }),
    },
    workbenchApi: {
      getManifest: vi.fn(),
      updateManifest: vi.fn(),
      uploadFiles: vi.fn(),
      lint: vi.fn(),
      simulate: vi.fn(),
      synthesize: vi.fn(),
      listRuns: vi.fn(),
      getRun: vi.fn(),
      getRunStatus: vi.fn(),
      pinRun: vi.fn(),
      compareRuns: vi.fn(),
    },
  };
});

import { useStore } from "@/lib/store";
import { workbenchApi, workspaceApi } from "@/lib/api";

const SESSION = {
  id: "s1",
  name: "s1",
  model_name: "claude-sonnet-4-6",
  project_id: null,
  created_at: null,
  updated_at: null,
  total_tokens: 0,
  total_cost: 0,
};

beforeEach(() => {
  vi.clearAllMocks();
  useStore.setState({
    currentSession: SESSION as any,
    runs: [],
    selectedRunId: null,
    lintResult: null,
    manifest: null,
    activeArtifactTab: "spec",
    selectedWaveform: null,
  });
});

// (Tool execution — lint/sim/synth — moved to lib/commands.ts; the old
// runLint/runSim/runSynth store actions and the console log were removed
// with the v1 chrome.)

describe("workbench store: selectRun loads the sim waveform", () => {
  it("selecting a sim run loads its isolated VCD and shows the waveform tab", async () => {
    const simRun = {
      id: "sim_0001",
      kind: "sim" as const,
      status: "failed" as const,
      createdAt: new Date().toISOString(),
      top: "cpu_tb",
      pinned: false,
      vcdPath: "sim_runs/sim_0001/dump.vcd",
      failure: { type: "test_failed", firstFailureLine: "ERROR", timeNs: 240 },
    };
    useStore.setState({ runs: [simRun] as any });

    await useStore.getState().selectRun("sim_0001");

    const s = useStore.getState();
    expect(s.selectedRunId).toBe("sim_0001");
    expect(s.activeArtifactTab).toBe("waveform");
    expect(workspaceApi.getWaveform).toHaveBeenCalledWith("s1", "sim_runs/sim_0001/dump.vcd");
    expect(s.selectedWaveform).toBe("sim_runs/sim_0001/dump.vcd");
  });
});

describe("workbench store: selectRun banner + synth report", () => {
  it("selecting a synth run loads its report and shows the report tab", async () => {
    const synthRun = {
      id: "synth_0002",
      kind: "synth" as const,
      status: "passed" as const,
      createdAt: new Date().toISOString(),
      top: "cpu_top",
      pinned: false,
      reportAvailable: true,
    };
    useStore.setState({ runs: [synthRun] as any });

    await useStore.getState().selectRun("synth_0002");

    const s = useStore.getState();
    expect(s.selectedRunId).toBe("synth_0002");
    expect(s.activeArtifactTab).toBe("report");
    expect(workspaceApi.getReport).toHaveBeenCalledWith("s1", "synth_0002");
  });
});

describe("workbench store: setFileRole", () => {
  it("persists a role override via the manifest endpoint", async () => {
    (workbenchApi.updateManifest as any).mockResolvedValue({
      sessionId: "s1",
      files: [{ name: "harness.v", role: "tb", path: "harness.v" }],
      synthTop: "",
      simTop: "harness",
      clockPeriodNs: 10,
      platform: "sky130hd",
    });

    await useStore.getState().setFileRole("harness.v", "tb");

    expect(workbenchApi.updateManifest).toHaveBeenCalledWith("s1", {
      files: [{ name: "harness.v", role: "tb" }],
    });
    expect(useStore.getState().manifest?.files[0].role).toBe("tb");
  });
});

describe("workbench store: refreshWorkspace surfaces load failures", () => {
  it("sets workspaceError when listFiles fails (not a silent empty workspace)", async () => {
    (workspaceApi.listFiles as any).mockRejectedValueOnce(new Error("Session not found"));
    useStore.setState({ workspaceError: null });

    await useStore.getState().refreshWorkspace();

    expect(useStore.getState().workspaceError).toMatch(/couldn't load/i);
  });

  it("clears workspaceError on a successful load", async () => {
    (workspaceApi.listFiles as any).mockResolvedValue([]);
    useStore.setState({ workspaceError: "stale error" });

    await useStore.getState().refreshWorkspace();

    expect(useStore.getState().workspaceError).toBeNull();
  });
});

describe("workbench store: pinRun", () => {
  it("optimistically updates the pinned flag", async () => {
    useStore.setState({
      runs: [{ id: "sim_0001", kind: "sim", status: "passed", createdAt: null, top: "tb", pinned: false }] as any,
    });
    (workbenchApi.pinRun as any).mockResolvedValue({ ok: true, runId: "sim_0001", pinned: true });

    await useStore.getState().pinRun("sim_0001", true);

    expect(useStore.getState().runs[0].pinned).toBe(true);
  });
});
