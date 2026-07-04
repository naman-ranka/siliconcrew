import { describe, it, expect, beforeEach, vi } from "vitest";

// Mock the API layer so these tests run with no backend (Tier 1, jsdom).
vi.mock("@/lib/api", () => ({
  projectsApi: {},
  sessionsApi: {},
  chatApi: {},
  threadsApi: {},
  modelsApi: {},
  workspaceApi: {},
  workbenchApi: {
    invokeTool: vi.fn(),
    updateManifest: vi.fn(),
    getManifest: vi.fn(),
    getToolCatalog: vi.fn(),
    getActivity: vi.fn().mockResolvedValue({ ok: true, events: [], nextBefore: null }),
  },
}));

import {
  CORE_SURFACE_COMMANDS,
  CORE_TWIN_TOOLS,
  buildSurfaceCommands,
  buildSurfacePayload,
  prettifyToolName,
  runSurfaceCommand,
  surfaceDefaults,
  toolToSurfaceCommand,
  type SurfaceCtx,
} from "@/lib/commandSurface";
import { useStore } from "@/lib/store";
import { workbenchApi } from "@/lib/api";
import type { RunSummary, ToolCatalogEntry } from "@/types";

// ---- fixtures -----------------------------------------------------------------

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

const MANIFEST = {
  sessionId: "s1",
  files: [
    { name: "alu.v", role: "rtl" as const, path: "alu.v" },
    { name: "tb.v", role: "tb" as const, path: "tb.v" },
  ],
  synthTop: "alu",
  simTop: "tb",
  clockPeriodNs: 10,
  platform: "sky130hd",
};

const synthRun = (id: string): RunSummary => ({
  id, kind: "synth", status: "passed", createdAt: null, top: "alu", pinned: false,
});

const CTX: SurfaceCtx = {
  manifest: MANIFEST,
  runs: [synthRun("synth_0002"), synthRun("synth_0001")],
  rootFiles: ["alu.v", "tb.v"],
};

const entry = (over: Partial<ToolCatalogEntry>): ToolCatalogEntry => ({
  name: "tool",
  description: "Does a thing.\nArgs:\n  x: something.",
  category: "essential",
  argsSchema: { type: "object", properties: {}, required: [] },
  requiresSignIn: false,
  async: false,
  mutates: false,
  ...over,
});

const CATALOG: ToolCatalogEntry[] = [
  entry({ name: "write_file", category: "essential", requiresSignIn: true, mutates: true,
    description: "Writes content to a file in the workspace.\nArgs:\n  filename: Name of the file.",
    argsSchema: {
      type: "object",
      properties: {
        filename: { type: "string" },
        content: { anyOf: [{ type: "string" }, { type: "null" }], default: null },
      },
      required: ["filename"],
    } }),
  // Core twins — must be skipped in favor of the hand-defined Flow commands.
  entry({ name: "linter_tool", category: "essential" }),
  entry({ name: "run_isolated_simulation", category: "essential", mutates: true }),
  entry({ name: "update_manifest", category: "manifest", requiresSignIn: true, mutates: true,
    description: "Upserts manifest fields.",
    argsSchema: {
      type: "object",
      properties: { updates_json: { type: "string" } },
      required: ["updates_json"],
    } }),
  entry({ name: "start_synthesis", category: "synthesis", async: true }),
  entry({ name: "retry_pd", category: "synthesis", async: true }),
  entry({ name: "get_synthesis_metrics", category: "synthesis", requiresSignIn: true,
    description: "Returns structured synthesis metrics for a run.\nParses standard ORFS outputs and returns JSON.",
    argsSchema: {
      type: "object",
      properties: { run_id: { anyOf: [{ type: "string" }, { type: "null" }], default: null } },
      required: [],
    } }),
  entry({ name: "search_logs_tool", category: "synthesis",
    description: "Searches for a keyword in OpenROAD logs and reports.\nArgs:\n  query: The string to search for.",
    argsSchema: {
      type: "object",
      properties: {
        query: { type: "string" },
        run_id: { anyOf: [{ type: "string" }, { type: "null" }], default: null },
      },
      required: ["query"],
    } }),
  entry({ name: "run_xls_flow", category: "hls", requiresSignIn: true, mutates: true,
    description: "Executes the entire high-level XLS synthesis flow.\nArgs:\n  dslx_file: Name of the DSLX file." }),
];

beforeEach(() => {
  vi.clearAllMocks();
  useStore.setState({
    currentSession: SESSION as never,
    manifest: MANIFEST,
    runs: CTX.runs,
    dirCache: {
      "": {
        status: "ready",
        entries: [
          { name: "alu.v", path: "alu.v", kind: "file" },
          { name: "sim_runs", path: "sim_runs", kind: "dir" },
        ],
        error: null,
      },
    },
    activity: { serverEvents: [], localEvents: [], status: "empty", nextBefore: null, error: null },
    toolCatalog: { tools: [], status: "empty", error: null },
  });
});

// ---- prettify -------------------------------------------------------------------

describe("prettifyToolName", () => {
  it("strips the _tool suffix and Title-Cases snake_case", () => {
    expect(prettifyToolName("get_synthesis_metrics")).toBe("Get Synthesis Metrics");
    expect(prettifyToolName("search_logs_tool")).toBe("Search Logs");
    expect(prettifyToolName("waveform_tool")).toBe("Waveform");
    expect(prettifyToolName("write_file")).toBe("Write File");
  });
});

// ---- buildSurfaceCommands ----------------------------------------------------------

describe("buildSurfaceCommands", () => {
  it("pins Flow (the core four) first, then catalog categories in first-seen order", () => {
    const { groups } = buildSurfaceCommands(CATALOG, CTX);
    expect(groups.map((g) => g.label)).toEqual([
      "Flow",
      "Essential",
      "Manifest",
      "Synthesis",
      "HLS",
    ]);
    expect(groups[0].commands).toBe(CORE_SURFACE_COMMANDS);
    expect(groups[0].commands.map((c) => c.id)).toEqual(["lint", "sim", "synth", "pnr"]);
  });

  it("skips catalog entries duplicating core twins", () => {
    const { groups } = buildSurfaceCommands(CATALOG, CTX);
    const generated = groups.slice(1).flatMap((g) => g.commands.map((c) => c.tool));
    for (const twin of Array.from(CORE_TWIN_TOOLS)) {
      expect(generated).not.toContain(twin);
    }
    // simulation_tool is also a twin even though this catalog doesn't carry it.
    expect(CORE_TWIN_TOOLS.has("simulation_tool")).toBe(true);
  });

  it("generates commands with prettified labels, short descs, and policy flags", () => {
    const { groups } = buildSurfaceCommands(CATALOG, CTX);
    const synthesis = groups.find((g) => g.label === "Synthesis")!;
    const metrics = synthesis.commands.find((c) => c.id === "get_synthesis_metrics")!;
    expect(metrics.label).toBe("Get Synthesis Metrics");
    expect(metrics.tool).toBe("get_synthesis_metrics");
    // Full docstring shortened — no Args section, keeps the summary lines.
    expect(metrics.desc).toBe(
      "Returns structured synthesis metrics for a run.\nParses standard ORFS outputs and returns JSON."
    );
    expect(metrics.requiresSignIn).toBe(true);
    expect(metrics.async).toBe(false);
    expect(metrics.core).toBeUndefined();
  });

  it("builds schema-driven params (run_id convention picker on Metrics)", () => {
    const { groups } = buildSurfaceCommands(CATALOG, CTX);
    const metrics = groups.flatMap((g) => g.commands).find((c) => c.id === "get_synthesis_metrics")!;
    expect(metrics.params).toHaveLength(1);
    expect(metrics.params[0]).toMatchObject({
      key: "run_id",
      editor: "enum",
      source: "run",
      optional: true,
      def: "",
    });
    expect(metrics.params[0].options).toEqual(["", "synth_0002", "synth_0001"]);
  });

  it("with an empty catalog only Flow renders (loading/error states)", () => {
    const { groups } = buildSurfaceCommands([], CTX);
    expect(groups).toHaveLength(1);
    expect(groups[0].label).toBe("Flow");
  });

  it("the synth core command describes the run_id-only dispatch contract (no job_id)", () => {
    const synth = CORE_SURFACE_COMMANDS.find((c) => c.id === "synth")!;
    expect(synth.desc).toContain("run_id");
    expect(synth.desc).not.toContain("job_id");
    expect(synth.desc).toContain("no client polling");
  });
});

// ---- payload from generated commands --------------------------------------------------

describe("buildSurfacePayload (schema-driven commands)", () => {
  it("omits optional empties, keeps required fields", () => {
    const search = toolToSurfaceCommand(
      CATALOG.find((e) => e.name === "search_logs_tool")!,
      CTX
    );
    const payload = buildSurfacePayload(search, { query: "slack" }, CTX);
    expect(payload).toEqual({ tool: "search_logs_tool", arguments: { query: "slack" } });
    // Choosing a run includes it.
    const withRun = buildSurfacePayload(search, { query: "slack", run_id: "synth_0001" }, CTX);
    expect(withRun.arguments).toEqual({ query: "slack", run_id: "synth_0001" });
  });

  it("defaults come from surfaceDefaults (run pickers pre-resolve options)", () => {
    const metrics = toolToSurfaceCommand(
      CATALOG.find((e) => e.name === "get_synthesis_metrics")!,
      CTX
    );
    expect(surfaceDefaults(metrics, CTX)).toEqual({ run_id: "" });
    expect(buildSurfacePayload(metrics, {}, CTX).arguments).toEqual({});
  });
});

// ---- runSurfaceCommand -------------------------------------------------------------------

describe("runSurfaceCommand", () => {
  it("POSTs /invoke for schema-driven commands and returns the result inline", async () => {
    vi.mocked(workbenchApi.invokeTool).mockResolvedValue({
      ok: true,
      tool: "get_synthesis_metrics",
      result: { status: "ok", metrics: { wns_ns: 0.85 } },
    });
    const metrics = toolToSurfaceCommand(
      CATALOG.find((e) => e.name === "get_synthesis_metrics")!,
      CTX
    );
    const res = await runSurfaceCommand(metrics, {});
    expect(workbenchApi.invokeTool).toHaveBeenCalledWith("s1", "get_synthesis_metrics", {});
    expect(res).toMatchObject({ ok: true, result: { status: "ok" } });
    // Optimistic activity: running → ok upsert landed in local events.
    const locals = useStore.getState().activity.localEvents;
    expect(locals.some((e) => e.tool === "get_synthesis_metrics" && e.status === "ok")).toBe(true);
  });

  it("surfaces invoke errors as { ok:false } with the message (and fieldErrors when attached)", async () => {
    const err = Object.assign(new Error("Invalid arguments"), {
      details: { fields: [{ field: "run_id", message: "unknown run" }] },
    });
    vi.mocked(workbenchApi.invokeTool).mockRejectedValue(err);
    const metrics = toolToSurfaceCommand(
      CATALOG.find((e) => e.name === "get_synthesis_metrics")!,
      CTX
    );
    const res = await runSurfaceCommand(metrics, { run_id: "synth_9999" });
    expect(res).toEqual({
      ok: false,
      result: "Invalid arguments",
      fieldErrors: [{ field: "run_id", message: "unknown run" }],
    });
  });

  it("message-only errors (actionFetch today) yield no fieldErrors", async () => {
    vi.mocked(workbenchApi.invokeTool).mockRejectedValue(new Error("boom"));
    const metrics = toolToSurfaceCommand(
      CATALOG.find((e) => e.name === "get_synthesis_metrics")!,
      CTX
    );
    const res = await runSurfaceCommand(metrics, {});
    expect(res).toMatchObject({ ok: false, result: "boom" });
    expect(res?.fieldErrors).toBeUndefined();
  });

  it("update_manifest parses updates_json and PUTs /manifest", async () => {
    vi.mocked(workbenchApi.updateManifest).mockResolvedValue(MANIFEST);
    vi.mocked(workbenchApi.getManifest).mockResolvedValue(MANIFEST);
    const cmd = toolToSurfaceCommand(CATALOG.find((e) => e.name === "update_manifest")!, CTX);
    const res = await runSurfaceCommand(cmd, { updates_json: '{"synthTop":"alu2"}' });
    expect(workbenchApi.updateManifest).toHaveBeenCalledWith("s1", { synthTop: "alu2" });
    expect(workbenchApi.invokeTool).not.toHaveBeenCalled();
    expect(res?.ok).toBe(true);
  });

  it("update_manifest rejects invalid JSON without calling the backend", async () => {
    const cmd = toolToSurfaceCommand(CATALOG.find((e) => e.name === "update_manifest")!, CTX);
    const res = await runSurfaceCommand(cmd, { updates_json: "{not json" });
    expect(res).toEqual({ ok: false, result: "updates_json is not valid JSON" });
    expect(workbenchApi.updateManifest).not.toHaveBeenCalled();
  });

  it("core commands delegate to runCommand and return null (Activity/Runs observe them)", async () => {
    // lint is core: no /invoke call, nothing to render inline.
    const res = await runSurfaceCommand(CORE_SURFACE_COMMANDS[0], {});
    expect(res).toBeNull();
    expect(workbenchApi.invokeTool).not.toHaveBeenCalled();
  });
});

// ---- store: toolCatalog slice ----------------------------------------------------------------

describe("store.loadToolCatalog", () => {
  it("loads once; a populated slice never re-loads", async () => {
    vi.mocked(workbenchApi.getToolCatalog).mockResolvedValue(CATALOG);
    await useStore.getState().loadToolCatalog();
    expect(useStore.getState().toolCatalog.status).toBe("ready");
    expect(useStore.getState().toolCatalog.tools).toHaveLength(CATALOG.length);
    await useStore.getState().loadToolCatalog();
    expect(workbenchApi.getToolCatalog).toHaveBeenCalledTimes(1);
  });

  it("concurrent calls share one fetch (single-flight)", async () => {
    vi.mocked(workbenchApi.getToolCatalog).mockResolvedValue(CATALOG);
    await Promise.all([
      useStore.getState().loadToolCatalog(),
      useStore.getState().loadToolCatalog(),
    ]);
    expect(workbenchApi.getToolCatalog).toHaveBeenCalledTimes(1);
  });

  it("503/tools_unavailable → status error with the message; explicit retry refetches", async () => {
    vi.mocked(workbenchApi.getToolCatalog)
      .mockRejectedValueOnce(new Error("The agent tool stack is not installed on this server."))
      .mockResolvedValueOnce(CATALOG);
    await useStore.getState().loadToolCatalog();
    expect(useStore.getState().toolCatalog).toMatchObject({
      status: "error",
      error: "The agent tool stack is not installed on this server.",
    });
    await useStore.getState().loadToolCatalog(); // the Retry button path
    expect(useStore.getState().toolCatalog.status).toBe("ready");
  });
});
