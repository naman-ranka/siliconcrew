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

/** Where the value comes from — drives the source badge next to the label. */
export function paramSourceFor(
  key: string,
  prop: SchemaProperty,
  hasConventionOptions: boolean,
  manifestHasValue = false
): SurfaceParamSource {
  const p = unwrapOptional(prop).prop;
  if (RUN_ID_KEYS.has(key) && hasConventionOptions) return "run";
  if (MANIFEST_KEYS.has(key)) return manifestHasValue ? "manifest" : "choice";
  if (Array.isArray(p.enum) && p.enum.length > 0) return "choice";
  if (hasConventionOptions) return "choice";
  if (p.default !== undefined) return "default";
  return "text";
}

/**
 * Live workspace choices for conventional keys; null when no convention
 * applies (the field falls back to its schema enum or free input).
 */
export function conventionOptions(key: string, ctx: SurfaceCtx): string[] | null {
  if (RUN_ID_KEYS.has(key)) {
    // Runs arrive newest-first from the backend.
    return ctx.runs.filter((r) => r.kind === "synth").map((r) => r.id);
  }
  if (key === "vcd_file") {
    return ctx.runs.filter((r) => r.kind === "sim" && r.vcdPath).map((r) => r.vcdPath as string);
  }
  if (key === "verilog_file") {
    return (ctx.manifest?.files ?? []).filter((f) => f.role === "rtl").map((f) => f.name);
  }
  if (key === "sby_file") return ctx.rootFiles.filter((f) => f.endsWith(".sby"));
  if (key === "dslx_file") return ctx.rootFiles.filter((f) => f.endsWith(".x"));
  if (key === "filename" || key === "file_path" || key === "spec_file") {
    return [...ctx.rootFiles];
  }
  return null;
}

/** Manifest value backing a conventional key, if the manifest supplies one. */
export function manifestValueFor(key: string, ctx: SurfaceCtx): unknown {
  const m = ctx.manifest;
  if (!m) return undefined;
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
  required: boolean
): unknown {
  const p = unwrapOptional(prop).prop;
  if (required) {
    const conv = conventionOptions(key, ctx);
    if (conv && conv.length > 0) return conv[0];
  }
  const fromManifest = manifestValueFor(key, ctx);
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
    const conv = conventionOptions(key, ctx);
    const hasConv = conv != null;

    let editor = editorFor(key, prop);
    // A plain string with live workspace choices (run ids, vcd paths, files)
    // upgrades from free text to a picker.
    if (editor === "text" && hasConv) editor = "enum";

    const enumOptions = Array.isArray(prop.enum) ? prop.enum.map(String) : undefined;
    let options: string[] | undefined = hasConv ? conv : enumOptions;
    // Optional single-choice fields keep an explicit "(omit)" entry.
    if (editor === "enum" && options && !required && !options.includes("")) {
      options = ["", ...options];
    }

    const isNumber = editor === "number";
    const min = isNumber ? prop.minimum ?? prop.exclusiveMinimum : undefined;
    const step = isNumber
      ? prop.multipleOf ?? (prop.type === "integer" ? 1 : 0.1)
      : undefined;

    const manifestVal = manifestValueFor(key, ctx);
    return {
      key,
      label: key,
      editor,
      source: paramSourceFor(key, raw ?? {}, hasConv, manifestVal !== undefined),
      ...(options ? { options } : {}),
      def: defaultFor(key, raw ?? {}, ctx, required),
      ...(min !== undefined ? { min } : {}),
      ...(step !== undefined ? { step } : {}),
      adv: basicOrAdvanced(key, required, hasConv) === "advanced",
      optional: !required,
      ...(typeof prop.description === "string" && prop.description
        ? { hint: prop.description }
        : {}),
    } satisfies SurfaceParam;
  });
}
