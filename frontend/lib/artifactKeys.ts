import type { ArtifactKind } from "@/types";

// Artifact keys are plain strings so they can live in Records, tab lists and
// localStorage. Formats:
//   code:<path>        — a workspace file open in the editor (path may contain
//                        slashes/dots; we split only on the FIRST ":")
//   spec               — the design spec (singleton, no ref)
//   wave:<runId>       — a run's waveform
//   wavefile:<path>    — a loose workspace VCD (not tied to a run)
//   report:<runId>     — a run's report
//   layout:<runId>     — a run's layout
//   schematic:<name>   — a schematic by file name
//   image:<path>       — a workspace image (png/jpg/webp/gif/svg)
//   data:<path>        — a workspace data file (csv/tsv/json/yaml)
//   text:<path>        — a workspace text file (txt/log/rpt)
//   interactive:<path> — an interactive sim dashboard (*.dashboard.html)
export type ArtifactKey = string;

const REF_KINDS: ReadonlySet<string> = new Set([
  "code",
  "wave",
  "wavefile",
  "report",
  "layout",
  "schematic",
  "image",
  "data",
  "text",
  "interactive",
]);

export interface ParsedArtifactKey {
  kind: ArtifactKind;
  ref: string | null;
}

export function makeArtifactKey(kind: ArtifactKind, ref?: string): ArtifactKey {
  if (kind === "spec") return "spec";
  return `${kind}:${ref ?? ""}`;
}

/** Parse an artifact key; returns null for anything that isn't a valid key. */
export function parseArtifactKey(key: string): ParsedArtifactKey | null {
  if (key === "spec") return { kind: "spec", ref: null };
  const i = key.indexOf(":");
  if (i <= 0) return null;
  const kind = key.slice(0, i);
  if (!REF_KINDS.has(kind)) return null;
  // Split only on the FIRST ":" — the ref (e.g. a file path) keeps the rest.
  return { kind: kind as ArtifactKind, ref: key.slice(i + 1) };
}
