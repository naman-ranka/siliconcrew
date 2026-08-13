import type { SchemaProperty, ToolCatalogEntry } from "@/types";
import type { SurfaceCtx, SurfaceParam, SurfaceParamSource } from "./commandSurface";

// JSON-Schema → form-model mapping for the Command Surface. PURE and
// CONVENTION-DRIVEN: no per-tool code lives here — every tool the backend
// catalogs renders through the same handful of key/type conventions, so a new
// backend tool appears in the UI with a sensible form for free.

// --- conventions ----------------------------------------------------------------

/** Keys that reference a synthesis run id (newest-first choices from live runs). */
const RUN_ID_KEYS = new Set(["run_id", "child_run_id", "parent_run_id", "source_run_id"]);

/** Keys whose default comes from the manifest when it has a value. */
const MANIFEST_KEYS = new Set([
  "platform",
  "clock_period_ns",
  "clockPeriodNs",
  "top_module",
  "sim_top",
  "verilog_file",
  "verilog_files",
]);

/** Keys that stay basic (visible) even when optional with no convention options. */
const BASIC_KEYS = new Set(["query", "stage", "mode", "generator"]);

/** Tools whose `filename` is a DSLX source (*.x), not a Verilog/any file. */
const DSLX_FILENAME_TOOLS = new Set(["run_dslx_interpreter", "compile_dslx_to_ir"]);

/** Tools whose `top_module` is an HLS function/proc — NOT in the manifest, so
 *  suggesting Verilog tops there would be dishonest. Free text instead. */
const HLS_TOP_TOOLS = new Set(["run_xls_flow", "compile_dslx_to_ir"]);

/** File-valued keys (get the "file" tag + role subtitles when in the manifest). */
const FILE_VALUE_KEYS = new Set([
  "filename",
  "script_file",
  "spec_filename",
  "yaml_path",
  "ir_filename",
  "opt_ir_filename",
  "sby_file",
  "dslx_file",
  "vcd_file",
  "verilog_file",
  "verilog_files",
]);

/** Module-valued keys (get the "module" tag + defining-file subtitles). */
const MODULE_VALUE_KEYS = new Set(["sim_top", "top_module", "module_name", "top_name", "python_module"]);

/** Workspace paths filtered by extension (case-insensitive). */
function pathsByExt(ctx: SurfaceCtx, exts: string[]): string[] {
  return ctx.wsPaths.filter((p) => {
    const lower = p.toLowerCase();
    return exts.some((e) => lower.endsWith(e));
  });
}

// --- schema unwrapping ------------------------------------------------------------

export interface UnwrappedProp {
  prop: SchemaProperty;
  nullable: boolean;
}

/**
 * Pydantic Optionals arrive as `anyOf: [{type: X}, {type: "null"}]` with the
 * default/description on the wrapper. Return the inner typed member merged
 * with the wrapper's own fields (default, description, …) + `nullable: true`.
 */
export function unwrapOptional(prop: SchemaProperty): UnwrappedProp {
  if (!Array.isArray(prop.anyOf) || prop.anyOf.length === 0) {
    return { prop, nullable: false };
  }
  const nullable = prop.anyOf.some((m) => m?.type === "null");
  const inner = prop.anyOf.find((m) => m && m.type !== "null") ?? {};
  const { anyOf: _drop, ...wrapper } = prop;
  return { prop: { ...inner, ...wrapper }, nullable };
}

// --- per-field mapping --------------------------------------------------------------

/** Which editor widget a property renders with (expects an unwrapped prop). */
export function editorFor(key: string, prop: SchemaProperty): SurfaceParam["editor"] {
  const p = unwrapOptional(prop).prop;
  if (Array.isArray(p.enum) && p.enum.length > 0 && (p.type === "string" || p.type == null)) {
    return "enum";
  }
  if (p.type === "boolean") return "bool";
  if (p.type === "integer" || p.type === "number") return "number";
  if (p.type === "array" && p.items?.type === "string") return "multi";
  // W7/A24: dict (build_interactive_sim.parameters) and list[dict]
  // (write_spec.ports) get a validated JSON textarea — they were untypeable
  // through the plain text input.
  if (p.type === "object") return "json";
  if (p.type === "array" && p.items?.type === "object") return "json";
  return "text";
}

/** The shape a json editor validates against (see SurfaceParam.jsonKind). */
export function jsonKindFor(prop: SchemaProperty): "object" | "array" | undefined {
  const p = unwrapOptional(prop).prop;
  if (p.type === "object") return "object";
  if (p.type === "array" && p.items?.type === "object") return "array";
  return undefined;
}

/** Where the value comes from — drives the source badge next to the label. */
export function paramSourceFor(
  key: string,
  prop: SchemaProperty,
  hasConventionOptions: boolean,
  manifestHasValue = false,
  toolName?: string
): SurfaceParamSource {
  const p = unwrapOptional(prop).prop;
  if (RUN_ID_KEYS.has(key) && hasConventionOptions) return "run";
  // HLS tops are NOT manifest-backed (see HLS_TOP_TOOLS) — honest free text.
  if (MANIFEST_KEYS.has(key) && !(key === "top_module" && toolName && HLS_TOP_TOOLS.has(toolName)))
    return manifestHasValue ? "manifest" : "choice";
  if (Array.isArray(p.enum) && p.enum.length > 0) return "choice";
  if (hasConventionOptions) return "choice";
  if (p.default !== undefined) return "default";
  return "text";
}

/** Distinct testbench top modules from the manifest's derived list. */
function testbenchModules(ctx: SurfaceCtx): string[] {
  return Array.from(new Set((ctx.manifest?.testbenches ?? []).map((t) => t.module)));
}

/**
 * Live workspace choices for conventional keys; null when no convention
 * applies (the field falls back to its schema enum or free input). File
 * suggestions are ws-relative PATHS from the recursive index, consistently.
 * `toolName` (optional) disambiguates keys whose meaning is per-tool
 * (`filename` on DSLX/C++ tools, HLS `top_module`).
 */
export function conventionOptions(
  key: string,
  ctx: SurfaceCtx,
  toolName?: string
): string[] | null {
  if (RUN_ID_KEYS.has(key)) {
    // Runs arrive newest-first from the backend.
    return ctx.runs.filter((r) => r.kind === "synth").map((r) => r.id);
  }
  if (key === "vcd_file") {
    return ctx.runs.filter((r) => r.kind === "sim" && r.vcdPath).map((r) => r.vcdPath as string);
  }
  if (key === "verilog_file") {
    return (ctx.manifest?.files ?? []).filter((f) => f.role === "rtl").map((f) => f.path);
  }
  if (key === "verilog_files") {
    // Plural compile sets: the manifest's rtl + include paths.
    return (ctx.manifest?.files ?? [])
      .filter((f) => f.role === "rtl" || f.role === "include")
      .map((f) => f.path);
  }
  if (key === "sby_file") return pathsByExt(ctx, [".sby"]);
  if (key === "dslx_file") return pathsByExt(ctx, [".x"]);
  if (key === "script_file") return pathsByExt(ctx, [".py"]);
  if (key === "spec_filename" || key === "yaml_path") return pathsByExt(ctx, [".yaml", ".yml"]);
  if (key === "opt_ir_filename") return pathsByExt(ctx, [".opt.ir"]);
  if (key === "ir_filename") {
    // Unoptimized IR — the *.opt.ir outputs belong to opt_ir_filename.
    return pathsByExt(ctx, [".ir"]).filter((p) => !p.toLowerCase().endsWith(".opt.ir"));
  }
  if (key === "filename") {
    if (toolName && DSLX_FILENAME_TOOLS.has(toolName)) return pathsByExt(ctx, [".x"]);
    if (toolName === "experimental_compile_cpp_to_ir") return pathsByExt(ctx, [".cc"]);
    return [...ctx.wsPaths];
  }
  if (key === "sim_top") return testbenchModules(ctx);
  if (key === "top_module") {
    // HLS tops are DSLX functions / C++ classes — the manifest doesn't know
    // them, so no suggestions (free text; the hint says why).
    if (toolName && HLS_TOP_TOOLS.has(toolName)) return null;
    // Synth top first (the common answer), then every known testbench top.
    return Array.from(
      new Set(
        [ctx.manifest?.synthTop, ...testbenchModules(ctx)].filter((m): m is string => !!m)
      )
    );
  }
  return null;
}

/** "module" | "file" tag rendered next to the source badge, so the
 *  ".v-or-not" question answers itself; undefined for everything else. */
export function valueKindFor(key: string): "module" | "file" | undefined {
  if (MODULE_VALUE_KEYS.has(key)) return "module";
  if (FILE_VALUE_KEYS.has(key)) return "file";
  return undefined;
}

/**
 * Per-value subtitles for a key's combo suggestions: a module shows its
 * defining file; a file path shows its manifest role. Display-only.
 */
export function suggestionSubtitles(key: string, ctx: SurfaceCtx): Record<string, string> {
  const out: Record<string, string> = {};
  const m = ctx.manifest;
  if (MODULE_VALUE_KEYS.has(key)) {
    for (const t of m?.testbenches ?? []) {
      if (t.module && !(t.module in out)) out[t.module] = t.file;
    }
    return out;
  }
  if (FILE_VALUE_KEYS.has(key)) {
    for (const f of m?.files ?? []) {
      if (f.path && !(f.path in out)) out[f.path] = f.role;
    }
  }
  return out;
}

/** Manifest value backing a conventional key, if the manifest supplies one.
 *  Tool-aware: an HLS `top_module` is a DSLX function — the manifest's
 *  Verilog synthTop must NOT leak in as its default. */
export function manifestValueFor(key: string, ctx: SurfaceCtx, toolName?: string): unknown {
  const m = ctx.manifest;
  if (!m) return undefined;
  if (key === "top_module" && toolName && HLS_TOP_TOOLS.has(toolName)) return undefined;
  switch (key) {
    case "platform":
      return m.platform || undefined;
    case "clock_period_ns":
    case "clockPeriodNs":
      return m.clockPeriodNs ?? undefined;
    case "top_module":
      return m.synthTop || undefined;
    case "sim_top":
      return m.simTop || undefined;
    case "verilog_files": {
      // The manifest's compile set (rtl + include paths) — pre-filled so the
      // "manifest supplies files" default holds; the user edits, not rebuilds.
      const files = m.files
        .filter((f) => f.role === "rtl" || f.role === "include")
        .map((f) => f.path);
      return files.length > 0 ? files : undefined;
    }
    default:
      return undefined;
  }
}

/** Type-appropriate empty value (the "nothing chosen yet" state). */
function typeEmpty(prop: SchemaProperty): unknown {
  switch (prop.type) {
    case "integer":
    case "number":
      return 0;
    case "boolean":
      return false;
    case "array":
      return [];
    default:
      return "";
  }
}

/**
 * Field default: first convention option when the field is REQUIRED and the
 * workspace supplies choices (a required run_id defaults to the newest run);
 * manifest values for platform/clock/top keys; else the schema default; else
 * a type-appropriate empty.
 */
export function defaultFor(
  key: string,
  prop: SchemaProperty,
  ctx: SurfaceCtx,
  required: boolean,
  toolName?: string
): unknown {
  const p = unwrapOptional(prop).prop;
  // Array-valued fields never take a single suggestion as their default —
  // they fall through to the manifest set (verilog_files) or [].
  if (required && p.type !== "array") {
    const conv = conventionOptions(key, ctx, toolName);
    if (conv && conv.length > 0) return conv[0];
  }
  const fromManifest = manifestValueFor(key, ctx, toolName);
  if (fromManifest !== undefined) return fromManifest;
  if (p.default !== undefined && p.default !== null) return p.default;
  return typeEmpty(p);
}

/** Basic (always visible) vs advanced (collapsed) placement for a field. */
export function basicOrAdvanced(
  key: string,
  required: boolean,
  hasConventionOptions: boolean
): "basic" | "advanced" {
  if (required || hasConventionOptions || BASIC_KEYS.has(key)) return "basic";
  return "advanced";
}

/** The docstring's summary — everything before the "Args:" section / first blank line. */
export function shortDescription(full: string): string {
  let out = full ?? "";
  const argsIdx = out.search(/(^|\n)\s*Args:/);
  if (argsIdx >= 0) out = out.slice(0, argsIdx);
  const blank = out.indexOf("\n\n");
  if (blank >= 0) out = out.slice(0, blank);
  return out.trim();
}

// --- the form model -----------------------------------------------------------------

/**
 * Map one catalog entry's argsSchema to the Command Surface's existing
 * SurfaceParam shape. Options/defaults are resolved against the CURRENT ctx —
 * callers rebuild when the manifest/runs/root files change.
 */
export function buildFormModel(entry: ToolCatalogEntry, ctx: SurfaceCtx): SurfaceParam[] {
  const schema = entry.argsSchema ?? {};
  const properties = schema.properties ?? {};
  const requiredKeys = new Set(schema.required ?? []);

  return Object.entries(properties).map(([key, raw]) => {
    const { prop } = unwrapOptional(raw ?? {});
    const required = requiredKeys.has(key);
    const conv = conventionOptions(key, ctx, entry.name);
    const hasConv = conv != null;

    let editor = editorFor(key, prop);
    // A plain string with live workspace choices upgrades from free text to a
    // suggesting combobox — free entry stays allowed (the workspace scan can
    // miss things). run_id-family keys are the exception: runs ARE a closed
    // set, so they keep the honest closed picker.
    if (editor === "text" && hasConv) editor = RUN_ID_KEYS.has(key) ? "enum" : "combo";

    const enumOptions = Array.isArray(prop.enum) ? prop.enum.map(String) : undefined;
    let options: string[] | undefined = hasConv ? conv : enumOptions;
    // Optional single-choice fields keep an explicit "(omit)" entry (combos
    // don't need one — clearing the text omits the field).
    if (editor === "enum" && options && !required && !options.includes("")) {
      options = ["", ...options];
    }

    const isNumber = editor === "number";
    const min = isNumber ? prop.minimum ?? prop.exclusiveMinimum : undefined;
    const step = isNumber
      ? prop.multipleOf ?? (prop.type === "integer" ? 1 : 0.1)
      : undefined;

    const manifestVal = manifestValueFor(key, ctx, entry.name);
    const valueKind = valueKindFor(key);
    const jsonKind = editor === "json" ? jsonKindFor(prop) : undefined;
    // json editors hold TEXT: a structured schema default renders as pretty
    // JSON; empty/absent stays "" (omitted from the payload).
    let def = defaultFor(key, raw ?? {}, ctx, required, entry.name);
    if (editor === "json" && typeof def !== "string") {
      def =
        def == null || (Array.isArray(def) && def.length === 0)
          ? ""
          : JSON.stringify(def, null, 2);
    }
    // HLS top_module has NO suggestions by design — say why, honestly.
    const hlsTopHint =
      key === "top_module" && HLS_TOP_TOOLS.has(entry.name)
        ? "DSLX function / proc name — not tracked by the manifest"
        : undefined;
    return {
      key,
      label: key,
      editor,
      source: paramSourceFor(key, raw ?? {}, hasConv, manifestVal !== undefined, entry.name),
      ...(options ? { options } : {}),
      def,
      ...(min !== undefined ? { min } : {}),
      ...(step !== undefined ? { step } : {}),
      adv: basicOrAdvanced(key, required, hasConv) === "advanced",
      optional: !required,
      ...(jsonKind ? { jsonKind } : {}),
      ...(valueKind ? { valueKind } : {}),
      ...(valueKind ? { subtitles: (c: SurfaceCtx) => suggestionSubtitles(key, c) } : {}),
      ...(typeof prop.description === "string" && prop.description
        ? { hint: prop.description }
        : hlsTopHint
          ? { hint: hlsTopHint }
          : {}),
    } satisfies SurfaceParam;
  });
}
