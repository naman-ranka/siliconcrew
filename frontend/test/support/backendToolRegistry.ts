import fs from "node:fs";
import path from "node:path";

/**
 * The REAL tool registry, read from the backend source the frontend talks to.
 *
 * `src/api/tool_catalog.py`'s `build_catalog()` introspects the `@tool`
 * wrappers in `src/tools/wrappers.py` and serves each tool's name, category and
 * policy flags to the UI. A vitest run has no Python, so this reads the same
 * declarations straight out of that file — no checked-in snapshot to go stale,
 * which is the whole point: the coverage test must fail when a tool is renamed,
 * merged or deleted, not when someone forgets to regenerate a fixture.
 *
 * The parse is deliberately strict. If wrappers.py changes shape, this throws
 * loudly rather than reporting an empty registry that would make every
 * completeness assertion vacuously pass.
 */

export interface BackendTool {
  name: string;
  category: string;
  protected: boolean;
  mutates: boolean;
  asyncJob: boolean;
  surfaces: string[];
}

const WRAPPERS = path.resolve(__dirname, "../../../src/tools/wrappers.py");

/** `@policy(...)` argument text → the fields we care about. */
function parsePolicyArgs(argText: string): Omit<BackendTool, "name"> {
  const str = (key: string): string | null =>
    new RegExp(`${key}\\s*=\\s*"([^"]*)"`).exec(argText)?.[1] ?? null;
  const bool = (key: string): boolean | null => {
    const m = new RegExp(`${key}\\s*=\\s*(True|False)`).exec(argText);
    return m ? m[1] === "True" : null;
  };

  const category = str("category");
  const isProtected = bool("protected");
  const mutates = bool("mutates");
  const asyncJob = bool("async_job");
  if (category === null || isProtected === null || mutates === null || asyncJob === null) {
    throw new Error(`unparseable @policy(...) in wrappers.py: ${argText}`);
  }

  // surfaces=ALL_SURFACES | ("agent", "mcp") | ("agent",) | frozenset({...})
  const rawSurfaces =
    /surfaces\s*=\s*(ALL_SURFACES|frozenset\([^)]*\)|\([^)]*\)|\w+)/.exec(argText)?.[1]?.trim() ?? "";
  const surfaces = rawSurfaces.startsWith("ALL_SURFACES")
    ? ["agent", "mcp", "ui"]
    : Array.from(rawSurfaces.matchAll(/"(\w+)"/g)).map((m) => m[1]);
  if (surfaces.length === 0) {
    throw new Error(`unparseable surfaces= in wrappers.py: ${argText}`);
  }

  return { category, protected: isProtected, mutates, asyncJob, surfaces };
}

let cached: BackendTool[] | null = null;

/** Every registered tool, exactly as the backend declares it. */
export function backendTools(): BackendTool[] {
  if (cached) return cached;
  if (!fs.existsSync(WRAPPERS)) {
    throw new Error(
      `backend tool registry not found at ${WRAPPERS} — the frontend's tool ` +
        `coverage test must run from a full repo checkout`
    );
  }
  const src = fs.readFileSync(WRAPPERS, "utf8");

  // @policy( ... ) immediately above (or a comment away from) `def <name>(`.
  const blocks = Array.from(
    src.matchAll(/@policy\(([\s\S]*?)\)\n(?:#[^\n]*\n)*def\s+(\w+)\s*\(/g)
  );
  const tools = blocks.map(([, argText, name]) => ({
    name,
    ...parsePolicyArgs(argText),
  }));

  // Cross-check against the registry list itself, so a tool the regex missed
  // (or a tool defined but never registered) is a loud failure, not a silent
  // hole in every completeness assertion below.
  const listed = Array.from(
    /ALL_TOOLS\s*=\s*\[([\s\S]*?)\n\]/.exec(src)?.[1].matchAll(/^\s{4}(\w+),/gm) ?? []
  ).map((m) => m[1]);
  const parsed = new Set(tools.map((t) => t.name));
  const missing = listed.filter((n) => !parsed.has(n));
  const extra = tools.map((t) => t.name).filter((n) => !listed.includes(n));
  if (listed.length === 0 || missing.length > 0 || extra.length > 0) {
    throw new Error(
      `wrappers.py parse disagrees with ALL_TOOLS — missing [${missing}], extra [${extra}]`
    );
  }

  cached = tools;
  return tools;
}

/** The tools the Command Surface / REST /invoke get (catalog membership). */
export function uiCatalogTools(): BackendTool[] {
  return backendTools().filter((t) => t.surfaces.includes("ui"));
}

export function backendToolNames(): Set<string> {
  return new Set(backendTools().map((t) => t.name));
}
