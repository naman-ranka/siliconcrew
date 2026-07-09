import { workbenchApi } from "@/lib/api";
import {
  runCommand,
  testbenchChoices,
  type CommandId,
  LINT_ENGINES,
  PD_STAGES,
  PLATFORMS,
  SYNTH_STAGES,
} from "@/lib/commands";
import { buildFormModel, shortDescription } from "@/lib/schemaForm";
import { useStore } from "@/lib/store";
import type { ActivityEvent, DesignManifest, RunSummary, ToolCatalogEntry } from "@/types";

// The Command Surface: EVERY user-invocable tool as command → real tool call.
// The catalog is NOT hand-written — it renders from the backend's introspected
// tool registry (GET /tools; the same @tool schemas the agent and MCP clients
// use), mapped to forms by lib/schemaForm's conventions. Only the four core
// flow commands stay hand-defined: they mirror REST request bodies (which ARE
// their contract) and delegate to lib/commands' runCommand (dispatch + toasts;
// async runs complete via activity events). Everything else goes through the
// curated POST /invoke, so
// each run lands in the Activity feed with source "user" exactly like an agent
// call would with source "agent".

export type SurfaceParamSource = "manifest" | "choice" | "run" | "default" | "text";

export interface SurfaceCtx {
  manifest: DesignManifest | null;
  runs: RunSummary[];
  /** Workspace-root file names (from the dir cache) — file-picking conventions. */
  rootFiles: string[];
}

export interface SurfaceParam {
  key: string;
  label: string;
  /** "combo" = text input with filtered suggestions (resolveOptions); free
   *  entry always allowed — the "search ≻ suggest ≻ type anything" editor. */
  editor: "enum" | "number" | "bool" | "text" | "multi" | "combo";
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
  group: string;
  tool: string;
  desc: string;
  async?: boolean;
  requiresSignIn?: boolean;
  mutates?: boolean;
  /** Delegate execution to the core command engine (polling, unread, toasts). */
  core?: CommandId;
  autoArgs?: SurfaceAutoArg[];
  params: SurfaceParam[];
}

const filesByRoles = (m: DesignManifest | null, roles: string[]) =>
  (m?.files ?? []).filter((f) => roles.includes(f.role)).map((f) => f.name);

const synthRunIds = (ctx: SurfaceCtx) => ctx.runs.filter((r) => r.kind === "synth").map((r) => r.id);
const rtlFiles = (ctx: SurfaceCtx) => filesByRoles(ctx.manifest, ["rtl"]);

// ---- the core four (hand-defined; REST semantics + job polling) ----------------

export const CORE_SURFACE_COMMANDS: SurfaceCommand[] = [
  {
    id: "lint", label: "Lint", group: "Flow", tool: "linter_tool", core: "lint",
    desc: "Lint/syntax check (iverilog or verilator). Manifest supplies rtl + include files.",
    autoArgs: [{ key: "verilog_files", describe: (c: SurfaceCtx) => filesByRoles(c.manifest, ["rtl", "include"]).join(", ") || "—" }],
    params: [
      { key: "engine", label: "engine", editor: "enum", options: LINT_ENGINES, def: "auto", source: "choice" },
    ],
  },
  {
    id: "sim", label: "Simulate", group: "Flow", tool: "run_isolated_simulation", core: "sim", mutates: true,
    desc: "Manifest-driven sim in its own sim_runs/sim_NNNN/ dir — own VCD + provenance.",
    autoArgs: [
      { key: "reads (files)", describe: (c: SurfaceCtx) => filesByRoles(c.manifest, ["rtl", "tb", "include"]).join(", ") || "—" },
    ],
    params: [
      { key: "mode", label: "mode", editor: "enum", options: ["rtl", "post_synth"], def: "rtl", source: "choice" },
      {
        key: "simTop", label: "sim_top", editor: "combo", source: "manifest",
        options: (c: SurfaceCtx) => testbenchChoices(c.manifest),
        def: (c: SurfaceCtx) => c.manifest?.simTop ?? "",
        optional: true, // empty → backend falls back to the manifest default
        hint: "which testbench to run",
      },
    ],
  },
  {
    id: "synth", label: "Synthesize", group: "Flow", tool: "start_synthesis", core: "synth", async: true, requiresSignIn: true, mutates: true,
    desc: "Async ORFS job → { run_id } immediately; completion arrives via activity events / Refresh (no client polling).",
    autoArgs: [
      { key: "verilog_files", describe: (c: SurfaceCtx) => rtlFiles(c).join(", ") || "—" },
      { key: "top_module", describe: (c: SurfaceCtx) => c.manifest?.synthTop ?? "—" },
    ],
    params: [
      { key: "platform", label: "platform", editor: "enum", options: PLATFORMS, def: (c: SurfaceCtx) => c.manifest?.platform ?? "sky130hd", source: "manifest" },
      { key: "maxStage", label: "max_stage", editor: "enum", options: SYNTH_STAGES, def: "finish", source: "choice", hint: "“synth” = fast synthesis-only estimate" },
      { key: "clockPeriodNs", label: "clock_period_ns", editor: "number", def: (c: SurfaceCtx) => c.manifest?.clockPeriodNs ?? 10, min: 0.1, step: 0.1, unit: "ns", source: "manifest" },
      { key: "utilization", label: "utilization", editor: "number", def: 5, min: 1, max: 100, step: 1, unit: "%", source: "default", adv: true },
      { key: "aspectRatio", label: "aspect_ratio", editor: "number", def: 1.0, min: 0.1, step: 0.1, source: "default", adv: true },
      { key: "coreMargin", label: "core_margin", editor: "number", def: 2.0, min: 0, step: 0.5, unit: "µm", source: "default", adv: true },
      { key: "runEquiv", label: "run_equiv", editor: "bool", def: false, source: "default", adv: true },
    ],
  },
  {
    id: "pnr", label: "Place & Route", group: "Flow", tool: "retry_pd", core: "pnr", async: true, requiresSignIn: true, mutates: true,
    desc: "Branches a child PD run from an existing run and reruns downstream ORFS stages — first-class lineage.",
    params: [
      {
        key: "runId", label: "run_id", editor: "enum", source: "run",
        options: (ctx: SurfaceCtx) => synthRunIds(ctx),
        def: (ctx: SurfaceCtx) => synthRunIds(ctx)[0] ?? "",
        hint: "parent run to branch from",
      },
      { key: "fromStage", label: "start_stage", editor: "enum", options: PD_STAGES, def: "floorplan", source: "choice" },
      { key: "maxStage", label: "max_stage", editor: "enum", options: PD_STAGES, def: "finish", source: "choice" },
    ],
  },
];

// Catalog entries duplicating a core twin are skipped — the core versions
// carry the REST dispatch semantics the plain /invoke path lacks.
export const CORE_TWIN_TOOLS = new Set([
  "linter_tool",
  "run_isolated_simulation",
  "simulation_tool",
  "start_synthesis",
  "retry_pd",
]);

// ---- schema-driven catalog → surface commands -----------------------------------

const CATEGORY_LABELS: Record<string, string> = {
  essential: "Essential",
  manifest: "Manifest",
  verification: "Verification",
  synthesis: "Synthesis",
  editing: "Editing",
  reporting: "Reporting",
  hls: "HLS",
};

function categoryLabel(category: string): string {
  return (
    CATEGORY_LABELS[category] ??
    (category ? category.charAt(0).toUpperCase() + category.slice(1) : "Other")
  );
}

/** "search_logs_tool" → "Search Logs"; "get_synthesis_metrics" → "Get Synthesis Metrics". */
export function prettifyToolName(name: string): string {
  return name
    .replace(/_tool$/, "")
    .split("_")
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export function toolToSurfaceCommand(entry: ToolCatalogEntry, ctx: SurfaceCtx): SurfaceCommand {
  return {
    id: entry.name,
    label: prettifyToolName(entry.name),
    group: categoryLabel(entry.category),
    tool: entry.name,
    desc: shortDescription(entry.description),
    async: entry.async,
    requiresSignIn: entry.requiresSignIn,
    mutates: entry.mutates,
    params: buildFormModel(entry, ctx),
  };
}

export interface SurfaceGroups {
  groups: { label: string; commands: SurfaceCommand[] }[];
}

/**
 * The whole surface: "Flow" (the core four) pinned first, then the backend
 * catalog's categories in first-seen order with pretty labels.
 */
export function buildSurfaceCommands(
  catalog: ToolCatalogEntry[],
  ctx: SurfaceCtx
): SurfaceGroups {
  const groups: { label: string; commands: SurfaceCommand[] }[] = [
    { label: "Flow", commands: CORE_SURFACE_COMMANDS },
  ];
  const byLabel = new Map<string, SurfaceCommand[]>();
  for (const entry of catalog) {
    if (CORE_TWIN_TOOLS.has(entry.name)) continue;
    const label = categoryLabel(entry.category);
    let bucket = byLabel.get(label);
    if (!bucket) {
      bucket = [];
      byLabel.set(label, bucket);
      groups.push({ label, commands: bucket });
    }
    bucket.push(toolToSurfaceCommand(entry, ctx));
  }
  return { groups };
}

// ---- value resolution + payload ---------------------------------------------------

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

export interface SurfaceFieldError {
  field: string;
  message: string;
}

export interface SurfaceRunResult {
  ok: boolean;
  /** Raw tool result (string or structured), for the surface's result pane. */
  result: unknown;
  /** Per-field messages from a 400 invalid_arguments response, when available. */
  fieldErrors?: SurfaceFieldError[];
}

// The api layer's actionFetch throws a plain Error carrying only the message
// (it does not attach the envelope's details today) — read details defensively
// so field-level errors light up if it ever starts attaching them.
function fieldErrorsFrom(e: unknown): SurfaceFieldError[] | undefined {
  const details = (e as { details?: { fields?: unknown } } | null)?.details;
  const fields = details?.fields;
  if (!Array.isArray(fields)) return undefined;
  const out = fields.filter(
    (f): f is SurfaceFieldError =>
      !!f && typeof f === "object" && typeof (f as SurfaceFieldError).field === "string"
  );
  return out.length > 0 ? out : undefined;
}

/** Live ctx for resolution — manifest, runs, and workspace-root file names. */
function storeCtx(): SurfaceCtx {
  const store = useStore.getState();
  return {
    manifest: store.manifest,
    runs: store.runs,
    rootFiles: (store.dirCache[""]?.entries ?? [])
      .filter((e) => e.kind === "file")
      .map((e) => e.name),
  };
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
  const ctx = storeCtx();

  if (cmd.core) {
    void runCommand(cmd.core, { ...surfaceDefaults(cmd, ctx), ...vals });
    return null; // observable via Activity/Runs; nothing to render inline
  }

  const { tool, arguments: args } = buildSurfacePayload(cmd, vals, ctx);

  if (cmd.tool === "update_manifest") {
    // Manifest edits use the dedicated PUT (same write path as the agent tool).
    // The introspected tool takes a single `updates_json` string — parse it to
    // the updates object PUT /manifest expects; other keys pass through as-is.
    let updates: Record<string, unknown>;
    const rawJson = args.updates_json;
    if (typeof rawJson === "string" && rawJson.trim()) {
      try {
        const parsed = JSON.parse(rawJson);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          return { ok: false, result: "updates_json must be a JSON object" };
        }
        updates = parsed as Record<string, unknown>;
      } catch {
        return { ok: false, result: "updates_json is not valid JSON" };
      }
    } else {
      const { updates_json: _drop, ...rest } = args;
      updates = rest;
    }
    const ev = localRunningEvent(tool, args);
    store.appendLocalActivity(ev);
    try {
      const res = await workbenchApi.updateManifest(session.id, updates);
      await store.loadManifest?.();
      store.appendLocalActivity({ ...ev, status: "ok", resultSummary: "manifest updated", durationMs: Date.now() - new Date(ev.ts).getTime() });
      return { ok: true, result: res };
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      store.appendLocalActivity({ ...ev, status: "error", resultSummary: msg, durationMs: Date.now() - new Date(ev.ts).getTime() });
      return { ok: false, result: msg, fieldErrors: fieldErrorsFrom(e) };
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
    return { ok: false, result: msg, fieldErrors: fieldErrorsFrom(e) };
  }
}
