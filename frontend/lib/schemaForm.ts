import type { FileRole, SchemaProperty, ToolCatalogEntry } from "@/types";
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

/**
 * File-valued argument names — the SAME rule the backend uses to decide which
 * args get workspace containment (`tool_catalog._looks_like_file_arg`:
 * `_FILE_ARG_SUFFIXES = ("_file", "_files", "_path")`, `_FILE_ARG_NAMES =
 * ("filename", "file_path")`). One rule, two mirrors — the keys the backend
 * contains are the keys the UI treats as files (FA3).
 */
export function isFileKey(key: string): boolean {
  return (
    key.endsWith("_file") ||
    key.endsWith("_files") ||
    key.endsWith("_path") ||
    key === "filename" ||
    key === "file_path"
  );
}

/** Module-valued argument names (`sim_top`, `top_module`, `python_module`,
 *  `module_name`, `top_name`) — by suffix, no enumerated list (FA4). */
const MODULE_KEY_RE = /(_module|_top)$|^module_name$|^top_name$/;

/** The stem of a file key: `verilog_files` → `verilog`, `spec_filename` →
 *  `spec`, `yaml_path` → `yaml`; `filename`/`file_path` have none. */
function fileKeyStem(key: string): string | null {
  const m = /^(.+?)_(file|files|filename|path)$/.exec(key);
  return m ? m[1] : null;
}

/** File-key STEM → extensions the suggested tier is filtered to. A convention
 *  table (stem → ext), not a tool list: a new tool with `foo_file` gets the
 *  whole index for free; unknown stems fall back to every workspace path. */
const EXTENSIONS_BY_STEM: Record<string, string[]> = {
  verilog: [".v", ".sv"],
  netlist: [".v"],
  sby: [".sby"],
  dslx: [".x"],
  script: [".py"],
  vcd: [".vcd"],
  spec: [".yaml", ".yml"],
  yaml: [".yaml", ".yml"],
};

/** Manifest roles the SUGGESTED tier draws from for verilog keys — manifest-
 *  first (the compile set is what the field MEANS); the extension-filtered
 *  index is the second tier (R43). Singular = a design file; plural = the
 *  compile set (rtl + include). */
const MANIFEST_ROLES: Record<string, FileRole[]> = {
  verilog_file: ["rtl"],
  verilog_files: ["rtl", "include"],
};

/** Workspace paths filtered by extension (case-insensitive). */
function pathsByExt(ctx: SurfaceCtx, exts: string[]): string[] {
  return ctx.wsPaths.filter((p) => {
    const lower = p.toLowerCase();
    return exts.some((e) => lower.endsWith(e));
  });
}

/** Ws-relative PATHS of the manifest files in the given roles (`name` is
 *  documented display-only in manifest.py — nested files break on it, A11). */
function manifestPaths(ctx: SurfaceCtx, roles: readonly FileRole[]): string[] {
  return (ctx.manifest?.files ?? []).filter((f) => roles.includes(f.role)).map((f) => f.path);
}

/** HLS tools' `top_module`/`module_name` name a DSLX function or proc — not a
 *  manifest module. One category-level rule reading backend policy (invariant
 *  2): the catalog's `category` is the honest source, never a tool-name set. */
const isHlsModuleKey = (key: string, category?: string): boolean =>
  category === "hls" && (key === "top_module" || key === "module_name");

const HLS_MODULE_HINT = "DSLX function / proc name — not tracked by the manifest";

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
  return "text";
}

/** Where the value comes from — drives the source badge next to the label.
 *  `category` = the catalog entry's category: on an HLS tool the module keys
 *  are not manifest-backed (honest free text). */
export function paramSourceFor(
  key: string,
  prop: SchemaProperty,
  hasConventionOptions: boolean,
  manifestHasValue = false,
  category?: string
): SurfaceParamSource {
  const p = unwrapOptional(prop).prop;
  if (RUN_ID_KEYS.has(key) && hasConventionOptions) return "run";
  if (MANIFEST_KEYS.has(key) && !isHlsModuleKey(key, category))
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
 * suggestions are ws-relative PATHS from the recursive index, consistently:
 * manifest roles first for verilog keys, else the index filtered by the
 * key's stem → extension table, else the whole index. `category` (optional)
 * is the catalog category — HLS module keys get no manifest suggestions.
 */
export function conventionOptions(
  key: string,
  ctx: SurfaceCtx,
  category?: string
): string[] | null {
  if (RUN_ID_KEYS.has(key)) {
    // Runs arrive newest-first from the backend.
    return ctx.runs.filter((r) => r.kind === "synth").map((r) => r.id);
  }
  if (key === "vcd_file") {
    // Run-derived: the sim runs' own VCDs (run dirs are outside the index).
    return ctx.runs.filter((r) => r.kind === "sim" && r.vcdPath).map((r) => r.vcdPath as string);
  }
  if (isFileKey(key)) {
    const roles = MANIFEST_ROLES[key];
    if (roles) return manifestPaths(ctx, roles);
    const stem = fileKeyStem(key);
    const exts = stem ? EXTENSIONS_BY_STEM[stem] : undefined;
    return exts ? pathsByExt(ctx, exts) : [...ctx.wsPaths];
  }
  if (key === "sim_top") return testbenchModules(ctx);
  if (key === "top_module") {
    // An HLS top is a DSLX function — the manifest doesn't know it (free text).
    if (isHlsModuleKey(key, category)) return null;
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
 *  ".v-or-not" question answers itself; undefined for everything else.
 *  Derived from the same key conventions as the suggestions (FA4). */
export function valueKindFor(key: string): "module" | "file" | undefined {
  if (isFileKey(key)) return "file";
  if (MODULE_KEY_RE.test(key)) return "module";
  return undefined;
}

/**
 * Per-value subtitles for a key's combo suggestions: a module shows its
 * defining file; a file path shows its manifest role. Display-only, keyed by
 * valueKind, not by key name.
 */
export function suggestionSubtitles(key: string, ctx: SurfaceCtx): Record<string, string> {
  const out: Record<string, string> = {};
  const m = ctx.manifest;
  const kind = valueKindFor(key);
  if (kind === "module") {
    for (const t of m?.testbenches ?? []) {
      if (t.module && !(t.module in out)) out[t.module] = t.file;
    }
  } else if (kind === "file") {
    for (const f of m?.files ?? []) {
      if (f.path && !(f.path in out)) out[f.path] = f.role;
    }
  }
  return out;
}

/** Manifest value backing a conventional SCALAR key, if the manifest supplies
 *  one. On an HLS tool `top_module` is a DSLX function — the manifest's
 *  Verilog synthTop must NOT leak in as its default. Plural file sets live in
 *  `manifestFileSet` — they are never a pre-filled field value. */
export function manifestValueFor(key: string, ctx: SurfaceCtx, category?: string): unknown {
  const m = ctx.manifest;
  if (!m) return undefined;
  if (isHlsModuleKey(key, category)) return undefined;
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
    default:
      return undefined;
  }
}

/**
 * The manifest set behind a PLURAL file key — the compile set (rtl + include
 * paths) for `verilog_files`. Owner refinement (2026-08-14): this is NOT a
 * pre-filled field value. Pre-filling turned every form into a wall of chips
 * the user had to read and prune; the field starts empty and this set is what
 * "empty" MEANS — said in the placeholder, and injected into the payload for
 * the tools that require the list (so the payload pane still shows the truth).
 */
export function manifestFileSet(key: string, ctx: SurfaceCtx): string[] | undefined {
  const roles = key.endsWith("_files") ? MANIFEST_ROLES[key] : undefined;
  if (!roles) return undefined;
  const files = manifestPaths(ctx, roles);
  return files.length > 0 ? files : undefined;
}

/** The honest "leave it empty and this is what runs" placeholder. */
export function manifestSetPlaceholder(set: string[]): string {
  return `manifest set (${set.length} file${set.length === 1 ? "" : "s"}) — type to override`;
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
  category?: string
): unknown {
  const p = unwrapOptional(prop).prop;
  // Array-valued fields never take a single suggestion as their default, and
  // (owner refinement 2026-08-14) never pre-fill the manifest set either:
  // plural file fields START EMPTY and mean the manifest set while empty.
  if (required && p.type !== "array") {
    const conv = conventionOptions(key, ctx, category);
    if (conv && conv.length > 0) return conv[0];
  }
  const fromManifest = manifestValueFor(key, ctx, category);
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
 * callers rebuild when the manifest/runs/path index change.
 */
export function buildFormModel(entry: ToolCatalogEntry, ctx: SurfaceCtx): SurfaceParam[] {
  const schema = entry.argsSchema ?? {};
  const properties = schema.properties ?? {};
  const requiredKeys = new Set(schema.required ?? []);
  const category = entry.category;

  return Object.entries(properties).map(([key, raw]) => {
    const { prop } = unwrapOptional(raw ?? {});
    const required = requiredKeys.has(key);
    const conv = conventionOptions(key, ctx, category);
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

    const manifestVal = manifestValueFor(key, ctx, category);
    // Plural file sets: the manifest backs the field (badge + placeholder +
    // payload injection) WITHOUT pre-filling it with chips.
    const mSet = editor === "multi" ? manifestFileSet(key, ctx) : undefined;
    const valueKind = valueKindFor(key);
    const hlsHint = isHlsModuleKey(key, category) ? HLS_MODULE_HINT : undefined;
    return {
      key,
      label: key,
      editor,
      source: paramSourceFor(
        key,
        raw ?? {},
        hasConv,
        manifestVal !== undefined || mSet !== undefined,
        category
      ),
      ...(options ? { options } : {}),
      def: defaultFor(key, raw ?? {}, ctx, required, category),
      // Empty plural file field = the manifest set. Say so in the input, and
      // — when the tool REQUIRES the list — put the set in the payload so the
      // pane shows what is actually sent (invariant 4).
      ...(mSet
        ? {
            manifestDefault: (c: SurfaceCtx) => manifestFileSet(key, c) ?? [],
            placeholder: manifestSetPlaceholder(mSet),
          }
        : {}),
      ...(required && editor === "multi" && key.endsWith("_files") && key in MANIFEST_ROLES
        ? { fillFromManifest: true as const }
        : {}),
      ...(min !== undefined ? { min } : {}),
      ...(step !== undefined ? { step } : {}),
      adv: basicOrAdvanced(key, required, hasConv) === "advanced",
      optional: !required,
      ...(valueKind ? { valueKind } : {}),
      ...(valueKind ? { subtitles: (c: SurfaceCtx) => suggestionSubtitles(key, c) } : {}),
      ...(typeof prop.description === "string" && prop.description
        ? { hint: prop.description }
        : hlsHint
          ? { hint: hlsHint }
          : {}),
    } satisfies SurfaceParam;
  });
}
