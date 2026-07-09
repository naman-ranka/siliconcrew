import type { RunSummary } from "@/types";

// Lineage grouping for the Runs table (BottomDock): retries (parentRunId) nest
// under the root of their chain, one indent level. Pure + unit-tested.

export interface RunGroup {
  root: RunSummary;
  children: RunSummary[];
}

function ts(r: RunSummary): number {
  if (!r.createdAt) return 0;
  const t = new Date(r.createdAt).getTime();
  return Number.isNaN(t) ? 0 : t;
}

/**
 * Group runs by lineage.
 * - Roots = runs with no parentRunId OR whose parent isn't in the list
 *   (orphan parent → treated as root). Roots are ordered newest-first.
 * - Children = all descendants of a root (retry chains flatten under the
 *   chain's root), ordered oldest-first.
 */
export function groupRuns(runs: RunSummary[]): RunGroup[] {
  const byId = new Map(runs.map((r) => [r.id, r]));
  const isRoot = (r: RunSummary) => !r.parentRunId || !byId.has(r.parentRunId);

  const groups = new Map<string, RunGroup>();
  const roots = runs.filter(isRoot).sort((a, b) => ts(b) - ts(a));
  for (const root of roots) groups.set(root.id, { root, children: [] });

  // Walk each non-root up its parent chain to the chain's root (cycle-safe).
  const rootOf = (r: RunSummary): RunSummary => {
    let cur = r;
    const seen = new Set<string>([cur.id]);
    while (cur.parentRunId && byId.has(cur.parentRunId)) {
      const parent = byId.get(cur.parentRunId)!;
      if (seen.has(parent.id)) break; // cycle guard
      cur = parent;
      seen.add(cur.id);
    }
    return cur;
  };

  for (const r of runs) {
    if (groups.has(r.id)) continue;
    const root = rootOf(r);
    const group = groups.get(root.id);
    if (group) {
      group.children.push(r);
    } else {
      // Degenerate (cycle with no reachable root) — surface the run anyway.
      groups.set(r.id, { root: r, children: [] });
    }
  }

  const result = Array.from(groups.values());
  for (const g of result) g.children.sort((a, b) => ts(a) - ts(b));
  return result;
}
