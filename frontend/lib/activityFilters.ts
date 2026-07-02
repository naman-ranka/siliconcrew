import type { ActivityEvent } from "@/types";

// Pure filtering helpers for the unified Activity feed (BottomDock). Kept
// store-free and DOM-free so they are trivially unit-testable.

export type ActivityKindFilter = "all" | "lint" | "sim" | "synth" | "writes";
export type ActivityToolKind = "lint" | "sim" | "synth" | "writes" | "other";
export type ActivityActorFilter = "both" | "agent" | "you";

const TOOL_KIND_MAP: Record<string, Exclude<ActivityToolKind, "other">> = {
  linter_tool: "lint",
  simulation_tool: "sim",
  run_isolated_simulation: "sim",
  start_synthesis: "synth",
  retry_pd: "synth",
  write_spec: "writes",
  write_file: "writes",
  edit_file_tool: "writes",
  apply_patch_tool: "writes",
};

/** Bucket a backend tool name into a feed kind. */
export function toolKind(tool: string): ActivityToolKind {
  const direct = TOOL_KIND_MAP[tool];
  if (direct) return direct;
  if (tool.startsWith("get_synthesis_")) return "synth";
  return "other";
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
