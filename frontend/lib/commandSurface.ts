import { workbenchApi } from "@/lib/api";
import {
  COMMANDS,
  RUN_ORDER,
  resolveParamDef,
  resolveParamOptions,
  runCommand,
  type CommandCtx,
  type CommandDef,
  type CommandId,
  type CommandParam,
} from "@/lib/commands";
import { TOOL } from "@/lib/toolNames";
import { buildFormModel, shortDescription, subtitlesByKind } from "@/lib/schemaForm";
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

export interface SurfaceCtx extends CommandCtx {
  /** Recursive workspace file PATHS (the store's path-index slice) — every
   *  file-picking convention suggests ws-relative paths, consistently. */
  wsPaths: string[];
  /** The backend truncated the path walk — suggestions may be incomplete;
   *  surfaced in the UI, never hidden (invariant 4). */
  wsPathsTruncated: boolean;
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
  /** L1: a file-set OVERRIDE param — rendered as the "Supplied by manifest"
   *  box (manifest chips, collapsed) with an "Override…" affordance that
   *  swaps in the multi-combo, not as a plain row. Empty value = the
   *  backend's manifest resolution, exactly as before. */
  override?: true;
  /** Module-valued vs file-valued — rendered as a tiny tag next to the source
   *  badge so the ".v here but not there" question answers itself. */
  valueKind?: "module" | "file";
  /** Per-value subtitles for combo suggestions (module → its file;
   *  file → its manifest role). Display-only decoration. */
  subtitles?: (ctx: SurfaceCtx) => Record<string, string>;
  /** Owner refinement (2026-08-14): the manifest set that backs a plural
   *  file field. The field itself starts EMPTY (no chip wall) — this is what
   *  the value MEANS when empty, so the placeholder can say it honestly and
   *  `fillFromManifest` can put it in the payload. */
  manifestDefault?: (ctx: SurfaceCtx) => string[];
  /** The tool REQUIRES the list (cocotb_tool / build_interactive_sim), so an
   *  empty field cannot mean "omit the key": buildSurfacePayload injects
   *  `manifestDefault` — and the payload pane shows exactly that (invariant
   *  4: what is sent is visible). Optional override params (lint/sim/synth)
   *  do NOT set this — empty stays "omit the key, backend resolves". */
  fillFromManifest?: true;
  /** Input placeholder — the honest "what happens if you leave this empty". */
  placeholder?: string;
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
  /** "Supplied by manifest" rows — resolved from lib/commands' one definition. */
  facts?: (ctx: SurfaceCtx) => { label: string; value: string }[];
  params: SurfaceParam[];
}

// ---- the core four: ONE definition, adapted ------------------------------------
//
// The flow commands live in lib/commands.ts (they mirror REST request bodies
// and dispatch through runCommand). This file used to restate all four —
// tool names, params, options, units, defaults — and the two copies drifted.
// It now adapts that single registry into the surface's own param shape.

const EDITOR_BY_TYPE: Record<CommandParam["type"], SurfaceParam["editor"]> = {
  enum: "enum",
  number: "number",
  boolean: "bool",
  text: "text",
  combo: "combo",
  files: "multi",
};

function toSurfaceParam(p: CommandParam): SurfaceParam {
  // A `files` registry param is file-valued by construction and renders as
  // the override box; its suggestions/subtitles come from the same resolver
  // the ⌘K modal reads (resolveParamOptions).
  const valueKind = p.type === "files" ? "file" : p.valueKind;
  return {
    key: p.key,
    label: p.label,
    editor: EDITOR_BY_TYPE[p.type],
    source: p.source,
    options: (ctx: SurfaceCtx) => resolveParamOptions(p, ctx),
    def: (ctx: SurfaceCtx) => resolveParamDef(p, ctx),
    unit: p.unit,
    step: p.step,
    min: p.min,
    max: p.max,
    adv: p.advanced,
    optional: p.optional,
    hint: p.hint,
    ...(p.type === "files" ? { override: true as const } : {}),
    ...(valueKind
      ? {
          valueKind,
          subtitles: (ctx: SurfaceCtx) => subtitlesByKind(valueKind, ctx.manifest),
        }
      : {}),
  };
}

function toSurfaceCommand(def: CommandDef): SurfaceCommand {
  return {
    id: def.id,
    label: def.label,
    group: "Flow",
    tool: def.tool,
    desc: def.description,
    async: def.async,
    core: def.id,
    facts: def.facts,
    params: def.params.map(toSurfaceParam),
  };
}

export const CORE_SURFACE_COMMANDS: SurfaceCommand[] = RUN_ORDER.map((id) =>
  toSurfaceCommand(COMMANDS[id])
);

// Catalog entries duplicating a core command are skipped — the core versions
// carry the REST dispatch semantics the plain /invoke path lacks. Read off the
// same registry, so a renamed tool cannot leave a stale entry behind.
export const CORE_TWIN_TOOLS = new Set<string>(RUN_ORDER.map((id) => COMMANDS[id].tool));

// ---- schema-driven catalog → surface commands -----------------------------------

// The catalog's categories ARE the grouping — this only fixes the casing of
// the ones title-casing gets wrong. Every other category (essential, manifest,
// verification, synthesis, editing, reporting, analysis, …) capitalizes
// correctly and needs no entry, so a new backend category groups itself.
const CATEGORY_LABEL_OVERRIDES: Record<string, string> = {
  hls: "HLS",
};

export function categoryLabel(category: string): string {
  return (
    CATEGORY_LABEL_OVERRIDES[category] ??
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
  // Sign-in gating and mutates are POLICY: read them off the catalog entry for
  // the core command's own tool rather than restating them here. `async` stays
  // declared in lib/commands because it describes the REST dispatch contract
  // (POST /synthesize returns a run id immediately) and must hold even when
  // the catalog fetch failed; the coverage test binds it to the tool's flag.
  const byName = new Map(catalog.map((e) => [e.name, e]));
  const core = CORE_SURFACE_COMMANDS.map((cmd) => {
    const entry = byName.get(cmd.tool);
    return entry
      ? { ...cmd, requiresSignIn: entry.requiresSignIn, mutates: entry.mutates }
      : cmd;
  });
  const groups: { label: string; commands: SurfaceCommand[] }[] = [
    { label: "Flow", commands: core },
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
    // Owner refinement (2026-08-14): a REQUIRED plural file field left empty
    // means "the manifest set" — inject it here so the payload pane shows the
    // exact list that goes on the wire. Optional override params never take
    // this branch: empty keeps meaning "omit the key" and the backend
    // resolves the manifest itself.
    if (p.fillFromManifest && Array.isArray(v) && v.length === 0) {
      const set = p.manifestDefault?.(ctx) ?? [];
      if (set.length > 0) {
        args[p.key] = set;
        return;
      }
    }
    if (p.optional && (v === "" || v == null || (Array.isArray(v) && v.length === 0))) return;
    if (v === undefined) return;
    if (p.editor === "number" && v !== "") v = Number(v);
    args[p.key] = v;
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

/** Live ctx for resolution — manifest, runs, and the recursive path index. */
function storeCtx(): SurfaceCtx {
  const store = useStore.getState();
  return {
    manifest: store.manifest,
    runs: store.runs,
    wsPaths: store.pathIndex.paths,
    wsPathsTruncated: store.pathIndex.truncated,
  };
}

/**
 * Execute a surface command. Core flow commands delegate to runCommand (which
 * owns unread/toasts) and are AWAITED so the caller's spinner and result pane
 * reflect what actually happened; the rest go through POST /invoke and return
 * their result for the inline result pane.
 */
export async function runSurfaceCommand(
  cmd: SurfaceCommand,
  vals: Record<string, unknown>
): Promise<SurfaceRunResult | null> {
  const store = useStore.getState();
  const session = store.currentSession;
  // Honest nothing-ran outcome — `null` from this function means exactly one
  // thing (async core dispatch succeeded), so the Surface's "Dispatched" note
  // can never appear when nothing was dispatched (dev#51 follow-up).
  if (!session) return { ok: false, result: "No active session" };
  const ctx = storeCtx();

  if (cmd.core) {
    // dev#51 (1): await the core engine so the Invoke spinner is truthful and
    // a failed invoke is visible right here — a detached `void runCommand`
    // left the Surface claiming "Dispatched" before the POST even ran.
    // runCommand still owns toasts/activity/unread; this only mirrors its
    // outcome into the Surface's own result pane. Nothing-ran outcomes
    // (duplicate in-flight, no session) arrive as ok:false/ran:false and
    // render as an inline error, never as "Dispatched".
    const outcome = await runCommand(cmd.core, { ...surfaceDefaults(cmd, ctx), ...vals });
    if (!outcome.ok) return { ok: false, result: outcome.summary };
    // Async dispatches keep the "Dispatched — follow it in Activity/Runs"
    // note (now rendered only after the dispatch actually succeeded); sync
    // cores render their real completion summary inline.
    return cmd.async ? null : { ok: true, result: outcome.summary };
  }

  const { tool, arguments: args } = buildSurfacePayload(cmd, vals, ctx);

  if (cmd.tool === TOOL.updateManifest) {
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
