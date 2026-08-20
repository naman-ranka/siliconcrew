// The frontend's ENTIRE hardcoded tool-name vocabulary, in one file.
//
// Everything the client can learn from the backend it reads from the catalog
// (GET /tools → `toolCatalog`): category, description, sign-in gating, async,
// mutates. What is left here is the small remainder that must be known BEFORE
// any catalog fetch — the reactions to live WebSocket tool frames, which arrive
// during an agent turn whether or not the Command Surface (the only thing that
// fetches /tools) was ever opened. Deriving those from a slice that is normally
// empty would be exactly the silent degradation this file exists to prevent.
//
// Because these names are a MIRROR of backend policy rather than a reading of
// it, they are bound to the real registry by test/toolRegistry.coverage.test.ts,
// which parses src/tools/wrappers.py: a renamed, merged or deleted tool turns
// that test red instead of quietly making the UI blander.
//
// The honest fix that would delete WORKSPACE_MUTATING_TOOLS: carry the tool's
// policy flags (at minimum `mutates`) on the WS `tool_call` frame, the way
// GET /tools already carries them.

/** Tool names referenced individually by the client (calls, single-tool
 *  checks). Named so the coverage test can prove each one still exists. */
export const TOOL = {
  linter: "linter_tool",
  simulation: "run_simulation",
  startSynthesis: "start_synthesis",
  retryPd: "retry_pd",
  getSynthesisStatus: "get_synthesis_status",
  updateManifest: "update_manifest",
  getManifest: "get_manifest",
} as const;

/**
 * Tools whose completion changes the workspace on disk — the client's mirror
 * of the backend's `mutates` policy flag. A completed call to any of these
 * invalidates the cached file tree and refreshes the manifest slice.
 *
 * Completeness is enforced: every tool the backend marks `mutates` must appear
 * here, or the coverage test fails.
 */
export const WORKSPACE_MUTATING_TOOLS: ReadonlySet<string> = new Set([
  "benchmark_xls",
  "build_interactive_sim",
  "cocotb_tool",
  "codegen_xls",
  "compile_dslx_to_ir",
  "edit_file",
  "generate_report_tool",
  "optimize_xls_ir",
  "retry_pd",
  "run_dslx_interpreter",
  "run_simulation",
  "run_python_analysis",
  "run_xls_flow",
  "sby_tool",
  "schematic_tool",
  "start_synthesis",
  "update_manifest",
  "write_file",
  "write_spec",
]);

/** Tools that write into a run directory — the extra dir prefix their output
 *  lands in, beyond the workspace root, and the reason they also move the Runs
 *  slice. Keys must be live tools (coverage test). */
export const RUN_DIR_PREFIX: Readonly<Record<string, string>> = {
  [TOOL.simulation]: "sim_runs",
  [TOOL.startSynthesis]: "synth_runs",
  [TOOL.retryPd]: "synth_runs",
};

/** dirCache prefixes a completed tool call invalidates; empty = nothing moved. */
export function dirsInvalidatedBy(tool: string): string[] {
  if (!WORKSPACE_MUTATING_TOOLS.has(tool)) return [];
  const runDir = RUN_DIR_PREFIX[tool];
  return runDir ? ["", runDir] : [""];
}

/** Whether a completed tool call can have changed `manifest.files` — any
 *  workspace mutation can (a new file, a deleted one, a role change). */
export function refreshesManifest(tool: string): boolean {
  return WORKSPACE_MUTATING_TOOLS.has(tool);
}

/** Whether a completed tool call can have added a row to the Runs slice —
 *  exactly the tools that write into a run directory. */
export function refreshesRuns(tool: string): boolean {
  return tool in RUN_DIR_PREFIX;
}

// --- reconnect hints (X2A-5) --------------------------------------------------
// Which trailing tool a dropped turn ended on decides the hint. Only synthesis
// dispatches leave a durable Runs record; agent sims are ephemeral (/tmp, no
// run row) and report inline only.

export const SYNTH_DISPATCH_TOOLS: ReadonlySet<string> = new Set<string>([
  TOOL.startSynthesis,
  TOOL.retryPd,
  // A turn that died on the status reader was watching a run that may well
  // still be going — the Runs panel is where to look.
  TOOL.getSynthesisStatus,
]);

export const SIM_TOOLS: ReadonlySet<string> = new Set<string>([TOOL.simulation]);
