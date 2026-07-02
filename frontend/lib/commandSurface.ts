import { workbenchApi } from "@/lib/api";
import { runCommand, type CommandId, PD_STAGES, PLATFORMS } from "@/lib/commands";
import { useStore } from "@/lib/store";
import type { ActivityEvent, DesignManifest, RunSummary } from "@/types";

// The Command Surface catalog: EVERY user-invocable tool — not just the four
// core flow commands — as command → real tool call, with the same contract as
// ⌘K: the manifest supplies files and targets (shown, never asked); the user
// supplies only choices. Core flow commands delegate to lib/commands'
// runCommand (job polling, unread marking); everything else goes through the
// curated POST /invoke endpoint, so each run lands in the Activity feed with
// source "user" exactly like an agent call would with source "agent".

export type SurfaceParamSource = "manifest" | "choice" | "run" | "default" | "text";

export interface SurfaceCtx {
  manifest: DesignManifest | null;
  runs: RunSummary[];
}

export interface SurfaceParam {
  key: string;
  label: string;
  editor: "enum" | "number" | "bool" | "text" | "multi";
  source: SurfaceParamSource;
  options?: readonly string[] | ((ctx: SurfaceCtx) => string[]);
  def: unknown | ((ctx: SurfaceCtx) => unknown);
  unit?: string;
  step?: number;
  min?: number;
  max?: number;
  adv?: boolean;
  optional?: boolean;
  hint?: string;
  when?: (vals: Record<string, unknown>) => boolean;
}

export interface SurfaceAutoArg {
  key: string;
  /** Human-readable resolution shown in the "Supplied by manifest" box. */
  describe: (ctx: SurfaceCtx) => string;
  /** Included in the displayed/sent payload when the tool expects it client-side. */
  value?: (ctx: SurfaceCtx) => unknown;
}

export interface SurfaceCommand {
  id: string;
  label: string;
  group: "Build" | "Verify" | "Analyze" | "Author" | "HLS";
  tool: string;
  desc: string;
  async?: boolean;
  /** Delegate execution to the core command engine (polling, unread, toasts). */
  core?: CommandId;
  autoArgs?: SurfaceAutoArg[];
  params: SurfaceParam[];
}

const filesByRoles = (m: DesignManifest | null, roles: string[]) =>
  (m?.files ?? []).filter((f) => roles.includes(f.role)).map((f) => f.name);

const synthRunIds = (ctx: SurfaceCtx) => ctx.runs.filter((r) => r.kind === "synth").map((r) => r.id);
const vcdPaths = (ctx: SurfaceCtx) =>
  ctx.runs.filter((r) => r.kind === "sim" && r.vcdPath).map((r) => r.vcdPath as string);
const rtlFiles = (ctx: SurfaceCtx) => filesByRoles(ctx.manifest, ["rtl"]);

const runIdParam = (opts?: { key?: string; optional?: boolean; hint?: string }): SurfaceParam => ({
  key: opts?.key ?? "run_id",
  label: opts?.key ?? "run_id",
  editor: "enum",
  source: "run",
  options: (ctx: SurfaceCtx) => (opts?.optional ? ["", ...synthRunIds(ctx)] : synthRunIds(ctx)),
  def: (ctx: SurfaceCtx) => (opts?.optional ? "" : synthRunIds(ctx)[0] ?? ""),
  optional: opts?.optional,
  hint: opts?.hint ?? (opts?.optional ? "omit = latest run" : undefined),
});

export const SURFACE_COMMANDS: SurfaceCommand[] = [
  // ---- Build (core flow — delegates to runCommand) ----
  {
    id: "lint", label: "Lint", group: "Build", tool: "linter_tool", core: "lint",
    desc: "Icarus syntax check. Manifest supplies rtl + include files.",
    autoArgs: [{ key: "verilog_files", describe: (c: SurfaceCtx) => filesByRoles(c.manifest, ["rtl", "include"]).join(", ") || "—" }],
    params: [],
  },
  {
    id: "sim", label: "Simulate", group: "Build", tool: "run_isolated_simulation", core: "sim",
    desc: "Manifest-driven sim in its own sim_runs/sim_NNNN/ dir — own VCD + provenance.",
    autoArgs: [
      { key: "sim_top", describe: (c: SurfaceCtx) => c.manifest?.simTop ?? "—" },
      { key: "reads (files)", describe: (c: SurfaceCtx) => filesByRoles(c.manifest, ["rtl", "tb", "include"]).join(", ") || "—" },
    ],
    params: [
      { key: "mode", label: "mode", editor: "enum", options: ["rtl", "post_synth"], def: "rtl", source: "choice" },
    ],
  },
  {
    id: "synth", label: "Synthesize", group: "Build", tool: "start_synthesis", core: "synth", async: true,
    desc: "Async ORFS job → { job_id, run_id } immediately, then honest polling.",
    autoArgs: [
      { key: "verilog_files", describe: (c: SurfaceCtx) => rtlFiles(c).join(", ") || "—" },
      { key: "top_module", describe: (c: SurfaceCtx) => c.manifest?.synthTop ?? "—" },
    ],
    params: [
      { key: "platform", label: "platform", editor: "enum", options: PLATFORMS, def: (c: SurfaceCtx) => c.manifest?.platform ?? "sky130hd", source: "manifest" },
      { key: "clockPeriodNs", label: "clock_period_ns", editor: "number", def: (c: SurfaceCtx) => c.manifest?.clockPeriodNs ?? 10, min: 0.1, step: 0.1, unit: "ns", source: "manifest" },
      { key: "utilization", label: "utilization", editor: "number", def: 5, min: 1, max: 100, step: 1, unit: "%", source: "default", adv: true },
      { key: "aspectRatio", label: "aspect_ratio", editor: "number", def: 1.0, min: 0.1, step: 0.1, source: "default", adv: true },
      { key: "coreMargin", label: "core_margin", editor: "number", def: 2.0, min: 0, step: 0.5, unit: "µm", source: "default", adv: true },
      { key: "runEquiv", label: "run_equiv", editor: "bool", def: false, source: "default", adv: true },
    ],
  },
  {
    id: "pnr", label: "Place & Route", group: "Build", tool: "retry_pd", core: "pnr", async: true,
    desc: "Branches a child PD run from an existing run and reruns downstream ORFS stages — first-class lineage.",
    params: [
      { ...runIdParam({ key: "runId", hint: "parent run to branch from" }), label: "run_id" },
      { key: "fromStage", label: "start_stage", editor: "enum", options: PD_STAGES, def: "floorplan", source: "choice" },
      { key: "maxStage", label: "max_stage", editor: "enum", options: PD_STAGES, def: "finish", source: "choice" },
    ],
  },

  // ---- Verify ----
  {
    id: "wave", label: "Waveform values", group: "Verify", tool: "waveform_tool",
    desc: "Extract VCD signal values in a time window — debug a failing sim without opening the viewer.",
    params: [
      { key: "vcd_file", label: "vcd_file", editor: "enum", source: "choice", options: (c: SurfaceCtx) => vcdPaths(c), def: (c: SurfaceCtx) => vcdPaths(c)[0] ?? "" },
      { key: "signals", label: "signals", editor: "multi", source: "choice", options: ["clk", "rst", "wr_en", "rd_en", "din", "dout", "full", "empty", "overflow"], def: ["clk", "full", "empty"] },
      { key: "start_time", label: "start_time", editor: "number", def: 0, min: 0, step: 5, unit: "ns", source: "default", adv: true },
      { key: "end_time", label: "end_time", editor: "number", def: 1000, min: 0, step: 50, unit: "ns", source: "default", adv: true },
    ],
  },
  {
    id: "cocotb", label: "cocotb", group: "Verify", tool: "cocotb_tool",
    desc: "Python testbench in the pinned reference container. Non-termination = FAIL. Sign-in required.",
    autoArgs: [
      { key: "verilog_files", describe: (c: SurfaceCtx) => filesByRoles(c.manifest, ["rtl", "tb", "include"]).join(", ") || "—" },
      { key: "top_module", describe: (c: SurfaceCtx) => c.manifest?.synthTop ?? "—", value: (c: SurfaceCtx) => c.manifest?.synthTop ?? "" },
    ],
    params: [{ key: "python_module", label: "python_module", editor: "text", def: "", source: "text", hint: "e.g. verif.test_fifo" }],
  },
  {
    id: "sby", label: "Formal (SBY)", group: "Verify", tool: "sby_tool",
    desc: "SymbiYosys property proof (smtbmc z3). Sign-in required.",
    params: [{ key: "sby_file", label: "sby_file", editor: "text", def: "", source: "text", hint: "workspace-relative .sby file" }],
  },

  // ---- Analyze ----
  {
    id: "metrics", label: "Metrics", group: "Analyze", tool: "get_synthesis_metrics",
    desc: "Structured PPA (WNS/TNS/area/cells/power) from ORFS outputs.",
    params: [runIdParam()],
  },
  {
    id: "stage_status", label: "Stage status", group: "Analyze", tool: "get_stage_status",
    desc: "Per-stage statuses + current stage for a run.",
    params: [runIdParam()],
  },
  {
    id: "stage_report", label: "Stage report", group: "Analyze", tool: "read_stage_report",
    desc: "Main ORFS artifact for one PD stage.",
    params: [
      { key: "stage", label: "stage", editor: "enum", options: PD_STAGES, def: "route", source: "choice" },
      runIdParam({ optional: true }),
    ],
  },
  {
    id: "drc", label: "Route DRC", group: "Analyze", tool: "get_route_drc_summary",
    desc: "Final-route DRC summary (empty report = clean).",
    params: [runIdParam({ optional: true })],
  },
  {
    id: "cts", label: "CTS", group: "Analyze", tool: "get_cts_summary",
    desc: "Clock-tree timing, skew, violation counts.",
    params: [runIdParam({ optional: true })],
  },
  {
    id: "congestion", label: "Congestion", group: "Analyze", tool: "get_congestion_summary",
    desc: "Global-route per-layer usage + overflow.",
    params: [runIdParam({ optional: true })],
  },
  {
    id: "compare", label: "Compare PD runs", group: "Analyze", tool: "compare_pd_runs",
    desc: "Child PD run vs its parent (lineage-aware).",
    params: [
      runIdParam({ key: "child_run_id" }),
      runIdParam({ key: "parent_run_id", optional: true, hint: "omit = infer from lineage" }),
    ],
  },
  {
    id: "search", label: "Search logs", group: "Analyze", tool: "search_logs_tool",
    desc: "Keyword grep across OpenROAD logs/reports.",
    params: [
      { key: "query", label: "query", editor: "text", def: "slack", source: "text" },
      runIdParam({ optional: true }),
    ],
  },
  {
    id: "schematic", label: "Schematic", group: "Analyze", tool: "schematic_tool",
    desc: "Yosys SVG schematic of a module.",
    autoArgs: [{ key: "top_module", describe: (c: SurfaceCtx) => c.manifest?.synthTop ?? "—", value: (c: SurfaceCtx) => c.manifest?.synthTop ?? "" }],
    params: [
      { key: "verilog_file", label: "verilog_file", editor: "enum", source: "choice", options: (c: SurfaceCtx) => rtlFiles(c), def: (c: SurfaceCtx) => rtlFiles(c)[0] ?? "" },
    ],
  },

  // ---- Author ----
  {
    id: "manifest", label: "Set tops / clock / platform", group: "Author", tool: "update_manifest",
    desc: "Upsert manifest fields — UI edits and agent edits write the same object.",
    params: [
      { key: "synthTop", label: "synthTop", editor: "text", source: "choice", def: (c: SurfaceCtx) => c.manifest?.synthTop ?? "" },
      { key: "simTop", label: "simTop", editor: "text", source: "choice", def: (c: SurfaceCtx) => c.manifest?.simTop ?? "" },
      { key: "clockPeriodNs", label: "clockPeriodNs", editor: "number", def: (c: SurfaceCtx) => c.manifest?.clockPeriodNs ?? 10, min: 0.1, step: 0.1, unit: "ns", source: "choice" },
      { key: "platform", label: "platform", editor: "enum", options: PLATFORMS, def: (c: SurfaceCtx) => c.manifest?.platform ?? "sky130hd", source: "choice" },
    ],
  },
  {
    id: "report", label: "Generate report", group: "Author", tool: "generate_report_tool",
    desc: "Spec-vs-results signoff report.",
    params: [runIdParam({ optional: true })],
  },
  {
    id: "save_metrics", label: "Save metrics", group: "Author", tool: "save_metrics_tool",
    desc: "Persist manually-found PPA values for the report. Sign-in required.",
    params: [
      { key: "wns_ns", label: "wns_ns", editor: "number", def: "", step: 0.01, unit: "ns", source: "text", optional: true },
      { key: "area_um2", label: "area_um2", editor: "number", def: "", step: 0.1, unit: "µm²", source: "text", optional: true },
      { key: "cell_count", label: "cell_count", editor: "number", def: "", step: 1, source: "text", optional: true, adv: true },
      { key: "power_uw", label: "power_uw", editor: "number", def: "", step: 1, unit: "µW", source: "text", optional: true, adv: true },
      runIdParam({ optional: true }),
    ],
  },

  // ---- HLS ----
  {
    id: "xls", label: "XLS flow (DSLX→Verilog)", group: "HLS", tool: "run_xls_flow",
    desc: "DSLX interpret → IR → optimize → codegen. Sign-in required.",
    params: [
      { key: "dslx_file", label: "dslx_file", editor: "text", def: "", source: "text", hint: "e.g. saturating_add.x" },
      { key: "top_module", label: "top_module", editor: "text", def: "", source: "text" },
      { key: "generator", label: "generator", editor: "enum", options: ["combinational", "pipeline"], def: "combinational", source: "choice" },
      { key: "pipeline_stages", label: "pipeline_stages", editor: "number", def: 0, min: 0, step: 1, source: "default", adv: true, when: (v) => v.generator === "pipeline" },
      { key: "clock_period_ps", label: "clock_period_ps", editor: "number", def: 0, min: 0, step: 50, unit: "ps", source: "default", adv: true },
      { key: "delay_model", label: "delay_model", editor: "enum", options: ["sky130", "asap7"], def: "sky130", source: "choice", adv: true },
      { key: "use_system_verilog", label: "use_system_verilog", editor: "bool", def: false, source: "default", adv: true },
    ],
  },
];

export const SURFACE_GROUPS = ["Build", "Verify", "Analyze", "Author", "HLS"] as const;

export function surfaceCommand(id: string): SurfaceCommand | undefined {
  return SURFACE_COMMANDS.find((c) => c.id === id);
}

export function resolveDef(p: SurfaceParam, ctx: SurfaceCtx): unknown {
  return typeof p.def === "function" ? (p.def as (c: SurfaceCtx) => unknown)(ctx) : p.def;
}

export function resolveOptions(p: SurfaceParam, ctx: SurfaceCtx): string[] {
  if (!p.options) return [];
  return typeof p.options === "function" ? p.options(ctx) : [...p.options];
}

export function surfaceDefaults(cmd: SurfaceCommand, ctx: SurfaceCtx): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  cmd.params.forEach((p) => { out[p.key] = resolveDef(p, ctx); });
  return out;
}

/** The exact payload shown in the right pane and sent to the backend. */
export function buildSurfacePayload(
  cmd: SurfaceCommand,
  vals: Record<string, unknown>,
  ctx: SurfaceCtx
): { tool: string; arguments: Record<string, unknown> } {
  const merged = { ...surfaceDefaults(cmd, ctx), ...vals };
  const args: Record<string, unknown> = {};
  cmd.params.forEach((p) => {
    if (p.when && !p.when(merged)) return;
    let v = merged[p.key];
    if (p.optional && (v === "" || v == null || (Array.isArray(v) && v.length === 0))) return;
    if (v === undefined) return;
    if (p.editor === "number" && v !== "") v = Number(v);
    args[p.key] = v;
  });
  cmd.autoArgs?.forEach((a) => {
    if (a.value) args[a.key] = a.value(ctx);
  });
  return { tool: cmd.tool, arguments: args };
}

// --- execution ----------------------------------------------------------------

let seq = 0;
function localRunningEvent(tool: string, args: Record<string, unknown>): ActivityEvent {
  return {
    id: `local:cs-${Date.now()}-${seq++}`,
    ts: new Date().toISOString(),
    source: "user",
    tool,
    args,
    status: "running",
    resultSummary: "",
    durationMs: null,
    runId: null,
    threadId: null,
  };
}

export interface SurfaceRunResult {
  ok: boolean;
  /** Raw tool result (string or structured), for the surface's result pane. */
  result: unknown;
}

/**
 * Execute a surface command. Core flow commands delegate to runCommand (which
 * owns polling/unread/toasts and returns nothing to display inline); the rest
 * go through POST /invoke and return their result for the inline result pane.
 */
export async function runSurfaceCommand(
  cmd: SurfaceCommand,
  vals: Record<string, unknown>
): Promise<SurfaceRunResult | null> {
  const store = useStore.getState();
  const session = store.currentSession;
  if (!session) return null;
  const ctx: SurfaceCtx = { manifest: store.manifest, runs: store.runs };

  if (cmd.core) {
    void runCommand(cmd.core, { ...surfaceDefaults(cmd, ctx), ...vals });
    return null; // observable via Activity/Runs; nothing to render inline
  }

  const { tool, arguments: args } = buildSurfacePayload(cmd, vals, ctx);

  if (cmd.tool === "update_manifest") {
    // Manifest edits use the dedicated PUT (same write path as the agent tool).
    const ev = localRunningEvent(tool, args);
    store.appendLocalActivity(ev);
    try {
      const res = await workbenchApi.updateManifest(session.id, args);
      await store.loadManifest?.();
      store.appendLocalActivity({ ...ev, status: "ok", resultSummary: "manifest updated", durationMs: Date.now() - new Date(ev.ts).getTime() });
      return { ok: true, result: res };
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      store.appendLocalActivity({ ...ev, status: "error", resultSummary: msg, durationMs: Date.now() - new Date(ev.ts).getTime() });
      return { ok: false, result: msg };
    }
  }

  const ev = localRunningEvent(tool, args);
  store.appendLocalActivity(ev);
  try {
    const res = await workbenchApi.invokeTool(session.id, tool, args);
    const summary = typeof res.result === "string" ? res.result.slice(0, 500) : JSON.stringify(res.result).slice(0, 500);
    useStore.getState().appendLocalActivity({
      ...ev, status: "ok", resultSummary: summary,
      durationMs: Date.now() - new Date(ev.ts).getTime(),
    });
    void useStore.getState().loadActivity();
    return { ok: true, result: res.result };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    useStore.getState().appendLocalActivity({
      ...ev, status: "error", resultSummary: msg,
      durationMs: Date.now() - new Date(ev.ts).getTime(),
    });
    void useStore.getState().loadActivity();
    return { ok: false, result: msg };
  }
}
