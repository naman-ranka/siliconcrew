import { describe, it, expect, beforeEach, vi } from "vitest";

// Mock the API layer so the command engine runs with no backend (Tier 1).
vi.mock("@/lib/api", () => ({
  projectsApi: {},
  sessionsApi: {},
  chatApi: {},
  threadsApi: {},
  modelsApi: {},
  workspaceApi: {},
  workbenchApi: {
    lint: vi.fn(),
    simulate: vi.fn(),
    synthesize: vi.fn(),
    retryRun: vi.fn(),
    getJob: vi.fn().mockResolvedValue({ status: "completed" }),
    listRuns: vi.fn().mockResolvedValue([]),
    getActivity: vi.fn().mockResolvedValue({ ok: true, events: [], nextBefore: null }),
  },
}));

import {
  COMMANDS,
  LINT_ENGINES,
  SYNTH_STAGES,
  defaultValues,
  manifestFacts,
  runCommand,
  testbenchChoices,
} from "@/lib/commands";
import { useStore } from "@/lib/store";
import { workbenchApi } from "@/lib/api";
import type { DesignManifest, LintResult, RunSummary } from "@/types";

const SESSION = {
  id: "s1",
  name: "s1",
  model_name: "m",
  project_id: null,
  created_at: null,
  updated_at: null,
  total_tokens: 0,
  total_cost: 0,
};

const MANIFEST: DesignManifest = {
  sessionId: "s1",
  files: [
    { name: "alu.v", role: "rtl", path: "alu.v" },
    { name: "alu_tb.v", role: "tb", path: "alu_tb.v" },
    { name: "cpu_tb.v", role: "tb", path: "tb/cpu_tb.v" },
  ],
  synthTop: "alu",
  simTop: "cpu_tb",
  clockPeriodNs: 10,
  platform: "sky130hd",
  testbenches: [
    { file: "tb/cpu_tb.v", module: "cpu_tb" },
    { file: "alu_tb.v", module: "alu_tb" },
  ],
  ignore: [],
};

const PASSING_LINT: LintResult = {
  status: "passed",
  warnings: [],
  errors: [],
  byFile: {},
  command: "verilator --lint-only -Wall alu.v",
  files: ["alu.v"],
  engine: "verilator",
};

const SIM_RUN: RunSummary = {
  id: "sim_0001",
  kind: "sim",
  status: "passed",
  createdAt: null,
  top: "cpu_tb",
  pinned: false,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(workbenchApi.getJob).mockResolvedValue({ status: "completed" });
  vi.mocked(workbenchApi.listRuns).mockResolvedValue([]);
  vi.mocked(workbenchApi.getActivity).mockResolvedValue({
    ok: true,
    events: [],
    nextBefore: null,
  } as never);
  useStore.setState({
    currentSession: SESSION as never,
    manifest: MANIFEST,
    runs: [],
    toasts: [],
    activity: { serverEvents: [], localEvents: [], status: "empty", nextBefore: null, error: null },
  });
});

// ---- registry shape ------------------------------------------------------------

describe("COMMANDS registry (verification-loop params)", () => {
  it("lint has the engine choice param", () => {
    const engine = COMMANDS.lint.params.find((p) => p.key === "engine")!;
    expect(engine.type).toBe("enum");
    expect(engine.options).toEqual(LINT_ENGINES);
    expect(engine.source).toBe("choice");
    expect(engine.advanced).toBeUndefined(); // basic
  });

  it("sim has the simTop combobox param (manifest-sourced, basic)", () => {
    const simTop = COMMANDS.sim.params.find((p) => p.key === "simTop")!;
    expect(simTop.type).toBe("combo");
    expect(simTop.source).toBe("manifest");
    expect(simTop.advanced).toBeUndefined();
  });

  it("synth has the maxStage enum param (basic — the fast estimate is headline)", () => {
    const maxStage = COMMANDS.synth.params.find((p) => p.key === "maxStage")!;
    expect(maxStage.type).toBe("enum");
    expect(maxStage.options).toEqual(SYNTH_STAGES);
    expect(maxStage.advanced).toBeUndefined();
  });
});

describe("defaultValues", () => {
  it("lint defaults engine=auto; synth defaults maxStage=finish", () => {
    expect(defaultValues("lint", { manifest: MANIFEST, runs: [] })).toEqual({ engine: "auto" });
    expect(defaultValues("synth", { manifest: MANIFEST, runs: [] })).toMatchObject({
      maxStage: "finish",
    });
  });

  it("sim defaults simTop from the manifest (empty without one)", () => {
    expect(defaultValues("sim", { manifest: MANIFEST, runs: [] })).toEqual({
      mode: "rtl",
      simTop: "cpu_tb",
    });
    expect(defaultValues("sim", { manifest: null, runs: [] })).toEqual({ mode: "rtl", simTop: "" });
  });
});

describe("testbenchChoices", () => {
  it("returns the distinct testbench modules from the manifest", () => {
    expect(testbenchChoices(MANIFEST)).toEqual(["cpu_tb", "alu_tb"]);
  });
  it("falls back to [simTop] on legacy manifests without testbenches", () => {
    expect(testbenchChoices({ ...MANIFEST, testbenches: [] })).toEqual(["cpu_tb"]);
    expect(testbenchChoices({ ...MANIFEST, testbenches: undefined })).toEqual(["cpu_tb"]);
    expect(testbenchChoices(null)).toEqual([]);
  });
});

describe("manifestFacts (sim)", () => {
  it("shows the default TB and the available-TB count", () => {
    const facts = manifestFacts("sim", { manifest: MANIFEST });
    expect(facts).toContainEqual({ label: "default tb", value: "cpu_tb" });
    expect(facts).toContainEqual({ label: "testbenches", value: "2 available" });
  });
});

// ---- request bodies --------------------------------------------------------------

describe("runCommand request bodies", () => {
  it("lint passes the chosen engine and summarizes with the resolved one", async () => {
    vi.mocked(workbenchApi.lint).mockResolvedValue({ ok: true, ...PASSING_LINT });
    await runCommand("lint", { engine: "verilator" });
    expect(workbenchApi.lint).toHaveBeenCalledWith("s1", { engine: "verilator" });
    expect(useStore.getState().toasts.some((t) => t.title.includes("(verilator)"))).toBe(true);
    const locals = useStore.getState().activity.localEvents;
    expect(locals.some((e) => e.resultSummary.includes("(verilator)"))).toBe(true);
  });

  it("lint defaults to engine=auto", async () => {
    vi.mocked(workbenchApi.lint).mockResolvedValue({ ok: true, ...PASSING_LINT, engine: null });
    await runCommand("lint");
    expect(workbenchApi.lint).toHaveBeenCalledWith("s1", { engine: "auto" });
    // No resolved engine → no engine tag in the toast.
    expect(useStore.getState().toasts.some((t) => t.title === "Lint passed")).toBe(true);
  });

  it("sim sends the manifest-default simTop on the fast path", async () => {
    vi.mocked(workbenchApi.simulate).mockResolvedValue(SIM_RUN);
    await runCommand("sim");
    expect(workbenchApi.simulate).toHaveBeenCalledWith("s1", { mode: "rtl", simTop: "cpu_tb" });
  });

  it("sim carries an overridden testbench (and omits an empty one)", async () => {
    vi.mocked(workbenchApi.simulate).mockResolvedValue(SIM_RUN);
    await runCommand("sim", { simTop: "alu_tb" });
    expect(workbenchApi.simulate).toHaveBeenLastCalledWith("s1", {
      mode: "rtl",
      simTop: "alu_tb",
    });
    await runCommand("sim", { simTop: "  " });
    expect(workbenchApi.simulate).toHaveBeenLastCalledWith("s1", { mode: "rtl" });
  });

  it("synth body carries maxStage", async () => {
    vi.mocked(workbenchApi.synthesize).mockResolvedValue({
      ok: true,
      jobId: "job_1",
      runId: "synth_0001",
    });
    void runCommand("synth", { maxStage: "synth" });
    await vi.waitFor(() =>
      expect(workbenchApi.synthesize).toHaveBeenCalledWith(
        "s1",
        expect.objectContaining({ maxStage: "synth", platform: "sky130hd" })
      )
    );
  });
});
