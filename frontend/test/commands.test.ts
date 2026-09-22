import { describe, it, expect, beforeEach, vi } from "vitest";

// Mock the API layer so the command engine runs with no backend (Tier 1).
vi.mock("@/lib/api", () => ({
  projectsApi: {},
  sessionsApi: {},
  chatApi: {},
  threadsApi: {},
  modelsApi: {},
  workspaceApi: {},
  // Mirrors the real detection: by CODE, never by message (W4/A17).
  isSignInRequired: (e: unknown) =>
    (e as { code?: string } | null)?.code === "signin_required",
  workbenchApi: {
    lint: vi.fn(),
    simulate: vi.fn(),
    synthesize: vi.fn(),
    retryRun: vi.fn(),
    listRuns: vi.fn().mockResolvedValue([]),
    getActivity: vi.fn().mockResolvedValue({ ok: true, events: [], nextBefore: null }),
  },
}));

import {
  COMMANDS,
  LINT_ENGINES,
  RUN_ORDER,
  SYNTH_STAGES,
  commandValuesForFile,
  defaultValues,
  manifestFacts,
  resolveParamOptions,
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

  // L1 (FA1): file overrides are a registry param TYPE — the key IS the REST
  // body key, the roles are the manifest roles the stage resolves.
  it("lint/sim declare `files`, synth declares `verilogFiles` — optional `type:\"files\"` params", () => {
    const lint = COMMANDS.lint.params.find((p) => p.key === "files")!;
    expect(lint).toMatchObject({ type: "files", optional: true, source: "manifest", roles: ["rtl", "include"] });
    const sim = COMMANDS.sim.params.find((p) => p.key === "files")!;
    expect(sim).toMatchObject({ type: "files", optional: true, roles: ["rtl", "tb", "include"] });
    const synth = COMMANDS.synth.params.find((p) => p.key === "verilogFiles")!;
    expect(synth).toMatchObject({ type: "files", optional: true, roles: ["rtl"] });
    expect(COMMANDS.pnr.params.some((p) => p.type === "files")).toBe(false);
  });

  it("`files` params resolve to manifest PATHS in their roles (nested files keep their path, FA2)", () => {
    const nested: DesignManifest = {
      ...MANIFEST,
      files: [
        { name: "nested.v", role: "rtl", path: "rtl/nested.v" },
        { name: "defs.vh", role: "include", path: "inc/defs.vh" },
        { name: "cpu_tb.v", role: "tb", path: "tb/cpu_tb.v" },
      ],
    };
    const ctx = { manifest: nested, runs: [] };
    const lint = COMMANDS.lint.params.find((p) => p.key === "files")!;
    expect(resolveParamOptions(lint, ctx)).toEqual(["rtl/nested.v", "inc/defs.vh"]);
    const synth = COMMANDS.synth.params.find((p) => p.key === "verilogFiles")!;
    expect(resolveParamOptions(synth, ctx)).toEqual(["rtl/nested.v"]);
    // Every override starts EMPTY (manifest-driven), on every command.
    for (const id of RUN_ORDER) {
      for (const p of COMMANDS[id].params.filter((x) => x.type === "files")) {
        expect(defaultValues(id, ctx)[p.key]).toEqual([]);
      }
    }
  });
});

describe("defaultValues", () => {
  it("lint defaults engine=auto; synth defaults maxStage=finish", () => {
    expect(defaultValues("lint", { manifest: MANIFEST, runs: [] })).toEqual({ engine: "auto", files: [] });
    expect(defaultValues("synth", { manifest: MANIFEST, runs: [] })).toMatchObject({
      maxStage: "finish",
    });
  });

  it("sim defaults simTop from the manifest (empty without one)", () => {
    expect(defaultValues("sim", { manifest: MANIFEST, runs: [] })).toEqual({
      mode: "rtl",
      files: [],
      simTop: "cpu_tb",
    });
    expect(defaultValues("sim", { manifest: null, runs: [] })).toEqual({ mode: "rtl", files: [], simTop: "" });
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

// dev#51 (2): right-click → Simulate on a testbench runs THAT testbench.
describe("commandValuesForFile", () => {
  it("sim on a known testbench file resolves its module as simTop", () => {
    expect(commandValuesForFile("sim", "tb/cpu_tb.v", MANIFEST)).toEqual({ simTop: "cpu_tb" });
    expect(commandValuesForFile("sim", "alu_tb.v", MANIFEST)).toEqual({ simTop: "alu_tb" });
  });

  it("sim on a non-testbench file passes nothing (manifest default applies)", () => {
    expect(commandValuesForFile("sim", "alu.v", MANIFEST)).toEqual({});
    expect(commandValuesForFile("sim", "alu_tb.v", null)).toEqual({});
  });

  it("lint passes the clicked file through the override (A15)", () => {
    expect(commandValuesForFile("lint", "alu_tb.v", MANIFEST)).toEqual({ files: ["alu_tb.v"] });
    expect(commandValuesForFile("lint", "rtl/alu.v", null)).toEqual({ files: ["rtl/alu.v"] });
  });

  it("sim does NOT single-file-override the compile set (a TB needs its deps, A15)", () => {
    const vals = commandValuesForFile("sim", "tb/cpu_tb.v", MANIFEST);
    expect(vals).toEqual({ simTop: "cpu_tb" });
    expect(vals).not.toHaveProperty("files");
  });

  it("synth passes nothing — a right-click must not silently drop the design", () => {
    expect(commandValuesForFile("synth", "alu.v", MANIFEST)).toEqual({});
  });
});

describe("manifestFacts (sim)", () => {
  it("shows the default TB and the available-TB count", () => {
    const facts = manifestFacts("sim", { manifest: MANIFEST });
    expect(facts).toContainEqual({ label: "default tb", value: "cpu_tb" });
    expect(facts).toContainEqual({ label: "testbenches", value: "2 available" });
  });
  it("file sets are no longer restated as facts — the `files` param IS the fact (FA22)", () => {
    for (const id of RUN_ORDER) {
      for (const f of manifestFacts(id, { manifest: MANIFEST })) {
        expect(["files", "sources"]).not.toContain(f.label);
      }
    }
    // Synth's constraints fact reads manifest PATHS (FA2).
    const withSdc: DesignManifest = {
      ...MANIFEST,
      files: [...MANIFEST.files, { name: "clk.sdc", role: "sdc", path: "constraints/clk.sdc" }],
    };
    expect(manifestFacts("synth", { manifest: withSdc })).toContainEqual({
      label: "constraints",
      value: "constraints/clk.sdc",
    });
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
    vi.mocked(workbenchApi.simulate).mockResolvedValue({ run: SIM_RUN, manifestWarnings: [] });
    await runCommand("sim");
    expect(workbenchApi.simulate).toHaveBeenCalledWith("s1", { mode: "rtl", simTop: "cpu_tb" });
  });

  it("sim carries an overridden testbench (and omits an empty one)", async () => {
    vi.mocked(workbenchApi.simulate).mockResolvedValue({ run: SIM_RUN, manifestWarnings: [] });
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
      runId: "synth_0001",
      pollAfterSec: 5,
    });
    await runCommand("synth", { maxStage: "synth" });
    expect(workbenchApi.synthesize).toHaveBeenCalledWith(
      "s1",
      expect.objectContaining({ maxStage: "synth", platform: "sky130hd" })
    );
  });

  // L1 (FA1): the `type:"files"` params ride the REST bodies through ONE
  // generic mapping — lint/sim `files`, synth `verilogFiles`; empty/absent
  // keeps the manifest set (the key is simply absent).

  it("lint carries a files override; an empty list is OMITTED (manifest-driven)", async () => {
    vi.mocked(workbenchApi.lint).mockResolvedValue({ ok: true, ...PASSING_LINT });
    await runCommand("lint", { files: ["alu_tb.v", "alu.v"] });
    expect(workbenchApi.lint).toHaveBeenLastCalledWith("s1", {
      engine: "auto",
      files: ["alu_tb.v", "alu.v"],
    });
    await runCommand("lint", { files: [] });
    expect(workbenchApi.lint).toHaveBeenLastCalledWith("s1", { engine: "auto" });
  });

  it("the ⌘K fast path (no values) sends today's body byte-for-byte with the files param present (L3/FA23)", async () => {
    vi.mocked(workbenchApi.lint).mockResolvedValue({ ok: true, ...PASSING_LINT });
    await runCommand("lint");
    expect(workbenchApi.lint).toHaveBeenLastCalledWith("s1", { engine: "auto" });
    vi.mocked(workbenchApi.simulate).mockResolvedValue({ run: SIM_RUN, manifestWarnings: [] });
    await runCommand("sim");
    expect(workbenchApi.simulate).toHaveBeenLastCalledWith("s1", { mode: "rtl", simTop: "cpu_tb" });
  });

  it("sim carries a files override alongside simTop", async () => {
    vi.mocked(workbenchApi.simulate).mockResolvedValue({ run: SIM_RUN, manifestWarnings: [] });
    await runCommand("sim", { simTop: "alu_tb", files: ["alu.v", "alu_tb.v"] });
    expect(workbenchApi.simulate).toHaveBeenLastCalledWith("s1", {
      mode: "rtl",
      simTop: "alu_tb",
      files: ["alu.v", "alu_tb.v"],
    });
  });

  it("synth carries a verilogFiles override; absent otherwise; blanks are dropped", async () => {
    vi.mocked(workbenchApi.synthesize).mockResolvedValue({
      ok: true,
      runId: "synth_0001",
      pollAfterSec: 5,
    });
    await runCommand("synth", { verilogFiles: ["rtl/alu.v", "", 7 as unknown as string] });
    expect(workbenchApi.synthesize).toHaveBeenLastCalledWith(
      "s1",
      expect.objectContaining({ verilogFiles: ["rtl/alu.v"] })
    );
    await runCommand("synth", {});
    const lastBody = vi.mocked(workbenchApi.synthesize).mock.calls.at(-1)![1];
    expect(lastBody).not.toHaveProperty("verilogFiles");
  });
});

// ---- dispatch-only async model (Wave 9: the UI never polls run status) ----------

describe("runCommand synth is dispatch-only", () => {
  it("dispatches, toasts, refreshes the run list once — and resolves without polling", async () => {
    vi.mocked(workbenchApi.synthesize).mockResolvedValue({
      ok: true,
      runId: "synth_0001",
      pollAfterSec: 5,
    });
    await runCommand("synth"); // resolves immediately — no job poll to wait on
    // The dispatch is narrated (toast + local activity event with the run id).
    expect(useStore.getState().toasts.some((t) => t.title === "Synthesis dispatched")).toBe(true);
    const locals = useStore.getState().activity.localEvents;
    expect(
      locals.some((e) => e.runId === "synth_0001" && /dispatched/.test(e.resultSummary))
    ).toBe(true);
    // The run list is pulled so the queued/running row appears.
    expect(workbenchApi.listRuns).toHaveBeenCalled();
    // No completion narration here — the store's transition detector owns it.
    expect(useStore.getState().toasts.some((t) => t.title === "Synthesis completed")).toBe(false);
  });

  it("retry_pd dispatch returns { runId } only", async () => {
    vi.mocked(workbenchApi.retryRun).mockResolvedValue({
      ok: true,
      runId: "synth_0002",
      pollAfterSec: 5,
    });
    useStore.setState({
      runs: [
        { id: "synth_0001", kind: "synth", status: "passed", createdAt: null, top: "alu", pinned: false },
      ] as never,
    });
    await runCommand("pnr", { runId: "synth_0001", fromStage: "place" });
    expect(workbenchApi.retryRun).toHaveBeenCalledWith("s1", "synth_0001", {
      fromStage: "place",
      maxStage: "finish",
    });
    expect(useStore.getState().toasts.some((t) => t.title === "P&R retry dispatched")).toBe(true);
  });
});

// ---- manifestWarnings surfacing (sc#66: the remaining frontend hop) --------------

describe("runCommand surfaces manifestWarnings", () => {
  const WARNING =
    "module 'GCN' is declared by both given/gcn.sv and solution/gcn.sv — " +
    "ignore one (manifest `ignore` glob) or change its role.";

  it("sim: warnings become toasts + an activity suffix, without altering the run result", async () => {
    vi.mocked(workbenchApi.simulate).mockResolvedValue({
      run: SIM_RUN, // still a PASSED run — warnings must not flip it
      manifestWarnings: [WARNING],
    });
    await runCommand("sim");
    const toasts = useStore.getState().toasts;
    // The warning renders as a warning (its own toast, full remedy text)...
    expect(toasts.some((t) => t.title === "Manifest warning" && t.detail === WARNING)).toBe(true);
    // ...and the run's own narration is unchanged (passed stays passed).
    expect(toasts.some((t) => t.kind === "success" && t.title === "Simulation passed")).toBe(true);
    const locals = useStore.getState().activity.localEvents;
    const ev = locals.find((e) => e.runId === "sim_0001" && e.status === "ok");
    expect(ev?.resultSummary).toBe("sim_0001 passed · 1 manifest warning");
  });

  it("synth: dispatch replies carry warnings too", async () => {
    vi.mocked(workbenchApi.synthesize).mockResolvedValue({
      ok: true,
      runId: "synth_0001",
      pollAfterSec: 5,
      manifestWarnings: [WARNING],
    });
    await runCommand("synth");
    const toasts = useStore.getState().toasts;
    expect(toasts.some((t) => t.title === "Manifest warning" && t.detail === WARNING)).toBe(true);
    // The dispatch itself still reads as a dispatch, not a failure.
    expect(toasts.some((t) => t.title === "Synthesis dispatched")).toBe(true);
    const locals = useStore.getState().activity.localEvents;
    expect(
      locals.some((e) => e.resultSummary === "synth_0001 dispatched · 1 manifest warning")
    ).toBe(true);
  });

  it("lint: the backend's notes reach the user (F5 — they were typed away and dropped)", async () => {
    const SCOPE_NOTE =
      "File-scoped lint: counter instantiated but not in the linted file set — " +
      "external modules were not elaborated.";
    vi.mocked(workbenchApi.lint).mockResolvedValue({
      ok: true,
      ...PASSING_LINT,
      manifestWarnings: [SCOPE_NOTE],
    });
    await runCommand("lint", { files: ["top.v"] });
    const toasts = useStore.getState().toasts;
    expect(toasts.some((t) => t.title === "Manifest warning" && t.detail === SCOPE_NOTE)).toBe(true);
    // The lint's own verdict is untouched — a note is a note (invariant 4).
    expect(toasts.some((t) => t.title.startsWith("Lint passed"))).toBe(true);
    const locals = useStore.getState().activity.localEvents;
    expect(locals.some((e) => e.resultSummary?.endsWith("· 1 manifest warning"))).toBe(true);
  });

  it("lint: no notes → no toast, no suffix", async () => {
    vi.mocked(workbenchApi.lint).mockResolvedValue({ ok: true, ...PASSING_LINT });
    await runCommand("lint");
    expect(useStore.getState().toasts.some((t) => t.title === "Manifest warning")).toBe(false);
    const locals = useStore.getState().activity.localEvents;
    expect(
      locals.some((e) => e.resultSummary === "passed (verilator) · 0 error(s), 0 warning(s)")
    ).toBe(true);
  });

  it("no warnings → no warning toast, no suffix", async () => {
    vi.mocked(workbenchApi.simulate).mockResolvedValue({ run: SIM_RUN, manifestWarnings: [] });
    await runCommand("sim");
    expect(useStore.getState().toasts.some((t) => t.title === "Manifest warning")).toBe(false);
    const locals = useStore.getState().activity.localEvents;
    expect(locals.some((e) => e.resultSummary === "sim_0001 passed")).toBe(true);
  });
});

// ---- double-submit guard is scoped by session --------------------------------

describe("runCommand double-submit guard is keyed by session + command", () => {
  // PR #92 review (adjacent to finding 2): the guard was a module-level Set of
  // bare command ids — the documented "in-memory registries keyed by bare ids
  // collide across workspaces" sharp edge. Session B's first Lint came back
  // "Lint is already running" about a call session A had made.
  it("the same command in session B while A's is in flight reaches the API", async () => {
    let resolveA!: (v: unknown) => void;
    vi.mocked(workbenchApi.lint).mockReturnValueOnce(
      new Promise((r) => {
        resolveA = r;
      }) as never
    );
    vi.mocked(workbenchApi.lint).mockResolvedValueOnce({ ok: true, ...PASSING_LINT } as never);
    const first = runCommand("lint"); // s1, in flight
    useStore.setState({ currentSession: { ...SESSION, id: "s2", name: "s2" } as never });
    const second = await runCommand("lint"); // s2 — a different workspace
    expect(second).toMatchObject({ ok: true, ran: true });
    expect(second.summary).not.toMatch(/already running/i);
    expect(workbenchApi.lint).toHaveBeenCalledTimes(2);
    expect(vi.mocked(workbenchApi.lint).mock.calls[1][0]).toBe("s2");
    resolveA({ ok: true, ...PASSING_LINT });
    await first;
  });

  it("a genuine same-session duplicate still short-circuits with the existing message", async () => {
    let resolveA!: (v: unknown) => void;
    vi.mocked(workbenchApi.lint).mockReturnValue(
      new Promise((r) => {
        resolveA = r;
      }) as never
    );
    const first = runCommand("lint");
    const dup = await runCommand("lint");
    expect(dup).toEqual({
      ok: false,
      summary: "Lint is already running — wait for it to finish",
      runId: null,
      ran: false,
    });
    expect(workbenchApi.lint).toHaveBeenCalledTimes(1);
    resolveA({ ok: true, ...PASSING_LINT });
    await first;
    // Released after settle: the next invoke runs.
    await runCommand("lint");
    expect(workbenchApi.lint).toHaveBeenCalledTimes(2);
  });
});
