import type { DesignManifest, DirEntry, SliceStatus } from "@/types";

// Pure helpers for the v2 FileExplorer: flatten the lazy dirCache into the
// row list the virtualizer renders, plus small manifest/run-dir heuristics.
// No store imports — everything is unit-testable with plain objects.

/** Structural subset of the store's DirSlice (lib/store.ts) — kept structural
 *  so tests (and any future caller) don't need the store. */
export interface DirSliceLike {
  status: SliceStatus;
  entries: DirEntry[];
  error?: string | null;
}

export interface FlatNode {
  entry: DirEntry;
  depth: number;
  /** Dir is currently expanded (files are always false). */
  expanded: boolean;
  /** Expanded dir whose children aren't cached yet — render a loading marker. */
  loading: boolean;
}

/**
 * Depth-first flatten of the cached tree, walking from the root slice ("").
 * Ordering is exactly the server's per-dir entry order (never re-sorted here).
 * - expanded dir with cached children → recurse (depth + 1)
 * - expanded dir with NO cached children (missing, or "loading" with nothing
 *   populated) → the dir row itself carries `loading: true`
 * - stale entries (status "revalidating"/"error" but populated) stay visible,
 *   matching the SWR iron rule.
 */
export function flattenTree(
  dirCache: Record<string, DirSliceLike | undefined>,
  expandedDirs: string[]
): FlatNode[] {
  const expanded = new Set(expandedDirs);
  const out: FlatNode[] = [];

  const walk = (dirPath: string, depth: number) => {
    const slice = dirCache[dirPath];
    if (!slice) return;
    for (const entry of slice.entries) {
      const isExpandedDir = entry.kind === "dir" && expanded.has(entry.path);
      if (!isExpandedDir) {
        out.push({ entry, depth, expanded: false, loading: false });
        continue;
      }
      const child = dirCache[entry.path];
      const populated = !!child && child.entries.length > 0;
      // Ready/revalidating slices can be walked even when empty (empty dir);
      // a missing or still-loading slice means "children unknown".
      const canRecurse =
        !!child && (populated || child.status === "ready" || child.status === "revalidating");
      out.push({
        entry,
        depth,
        expanded: true,
        loading: !child || (child.status === "loading" && !populated),
      });
      if (canRecurse) walk(entry.path, depth + 1);
    }
  };

  walk("", 0);
  return out;
}

const RUN_DIR_RE = /^(sim_runs|synth_runs)\/((sim|synth)_\d+)$/;

/** Run id for a dir entry that IS a run dir (sim_NNNN / synth_NNNN directly
 *  under sim_runs / synth_runs); null for everything else. */
export function runIdForDirEntry(entry: DirEntry): string | null {
  if (entry.kind !== "dir") return null;
  const m = RUN_DIR_RE.exec(entry.path);
  if (!m) return null;
  // Kind must match its parent (sim_runs/synth_0001 is not a run dir).
  if (m[1] === "sim_runs" && m[3] !== "sim") return null;
  if (m[1] === "synth_runs" && m[3] !== "synth") return null;
  return m[2];
}

/** Module-name heuristic: the client can't know module→file mapping, so we
 *  assume `foo.v` / `foo.sv` defines module `foo`. */
export function moduleNameForFile(name: string): string {
  return name.replace(/\.(v|sv)$/i, "");
}

/** Is this (root-level) file the synthesis top? rtl role + module heuristic. */
export function isSynthTopFile(name: string, manifest: DesignManifest | null): boolean {
  if (!manifest?.synthTop) return false;
  const f = manifest.files.find((x) => x.name === name);
  return !!f && f.role === "rtl" && moduleNameForFile(name) === manifest.synthTop;
}

/** Is this (root-level) file the simulation top? tb role + module heuristic. */
export function isSimTopFile(name: string, manifest: DesignManifest | null): boolean {
  if (!manifest?.simTop) return false;
  const f = manifest.files.find((x) => x.name === name);
  return !!f && f.role === "tb" && moduleNameForFile(name) === manifest.simTop;
}

/**
 * Validate a "New file" path (workspace-relative; slashes create folders
 * implicitly, git-style). Returns a human-readable error, or null when valid.
 */
export function validateNewFilePath(path: string): string | null {
  const p = path.trim();
  if (!p) return "Enter a file name";
  if (p.startsWith("/")) return "Use a workspace-relative path (no leading /)";
  if (p.split("/").some((seg) => seg === "" || seg === "." || seg === "..")) {
    return "Path must not contain empty, “.” or “..” segments";
  }
  return null;
}

/** Dir-cache prefixes to invalidate after creating `path`: the root plus every
 *  ancestor dir ("rtl/core/alu.v" → ["", "rtl", "rtl/core"]). */
export function dirPrefixesForPath(path: string): string[] {
  const out = [""];
  const parts = path.split("/").slice(0, -1);
  let acc = "";
  for (const part of parts) {
    acc = acc ? `${acc}/${part}` : part;
    out.push(acc);
  }
  return out;
}
