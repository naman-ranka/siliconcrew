import type { ActivityEvent } from "@/types";

// Pure filtering helpers for the unified Activity feed (BottomDock). Kept
// store-free and DOM-free so they are trivially unit-testable.

export type ActivityKindFilter = "all" | "lint" | "sim" | "synth" | "writes";
export type ActivityToolKind = "lint" | "sim" | "synth" | "writes" | "other";
export type ActivityActorFilter = "both" | "agent" | "you";

/**
 * Which feed pill a tool's events answer to. Kept as an explicit map rather
 * than read from the tool catalog: this runs on every activity row, in both
 * shells, long before the Command Surface has fetched GET /tools.
 *
 * "other" is an honest bucket — those events still render under All, they just
 * have no pill of their own — so this map is not required to be total. Two
 * things ARE enforced by test/toolRegistry.coverage.test.ts: every key is a
 * live tool, and every tool the backend files under the "synthesis" category
 * is bucketed "synth" (a prefix heuristic on `get_synthesis_` used to stand in
 * for that, and silently dropped read_stage_report, the summaries and
 * compare_pd_runs out of the Synth pill).
 */
export const TOOL_KIND_MAP: Record<string, Exclude<ActivityToolKind, "other">> = {
  linter_tool: "lint",
  run_simulation: "sim",
  start_synthesis: "synth",
  retry_pd: "synth",
  get_synthesis_status: "synth",
  get_synthesis_metrics: "synth",
  read_stage_report: "synth",
  get_route_drc_summary: "synth",
  get_cts_summary: "synth",
  get_congestion_summary: "synth",
  compare_pd_runs: "synth",
  search_logs_tool: "synth",
  schematic_tool: "synth",
  wait_for_synthesis: "synth",
  write_spec: "writes",
  write_file: "writes",
  edit_file: "writes",
};

/** Bucket a backend tool name into a feed kind. */
export function toolKind(tool: string): ActivityToolKind {
  return TOOL_KIND_MAP[tool] ?? "other";
}

export interface ActivityFilter {
  kind: ActivityKindFilter;
  errorsOnly: boolean;
  /** "agent" = source agent|mcp; "you" = source user. */
  actor: ActivityActorFilter;
  /** Case-insensitive match against tool / runId / resultSummary. */
  query: string;
}

export function filterActivity(
  events: ActivityEvent[],
  filter: ActivityFilter
): ActivityEvent[] {
  const q = filter.query.trim().toLowerCase();
  return events.filter((e) => {
    if (filter.kind !== "all" && toolKind(e.tool) !== filter.kind) return false;
    if (filter.errorsOnly && e.status !== "error") return false;
    if (filter.actor === "agent" && e.source === "user") return false;
    if (filter.actor === "you" && e.source !== "user") return false;
    if (q) {
      const hay = `${e.tool} ${e.runId ?? ""} ${e.resultSummary}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}
