import { parseArtifactKey, type ArtifactKey } from "@/lib/artifactKeys";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";

// THE single "open artifact" abstraction (v2 core idea): the file tree, run
// glyphs, activity rows, quick-open and chat links all resolve to an
// ArtifactKey and call this. Opening something already open focuses it; a
// run-scoped artifact clears that run's unread marker. Data loading is NOT
// done here — viewers load (and cache) their own data on mount, which is what
// makes keep-alive tabs free to revisit.
export function openArtifact(sessionId: string | null | undefined, key: ArtifactKey): void {
  if (!sessionId) return;
  const ui = useWorkbenchUiStore.getState();
  ui.openTab(sessionId, key);
  const parsed = parseArtifactKey(key);
  if (parsed?.ref && (parsed.kind === "wave" || parsed.kind === "report" || parsed.kind === "layout")) {
    ui.clearUnread(sessionId, parsed.ref);
  }
}

const RUN_DIR_PAT = /^(?:sim_runs|synth_runs)\/((?:sim|synth)_\d+)\//;

/** Run id a workspace path belongs to (sim_runs/<id>/… or synth_runs/<id>/…). */
export function runIdFromPath(path: string): string | null {
  return RUN_DIR_PAT.exec(path)?.[1] ?? null;
}

// Type-aware open routing for real files: artifacts with a dedicated viewer
// open in it (a VCD in the waveform viewer, a GDS in the layout viewer);
// everything else is code. Run-scoped artifacts key by run id so they share
// the tab/cache entry with the same artifact opened from the Runs panel.
// Extension families for the rich viewers (checked AFTER the run-scoped /
// schematic / spec routing above, so those keep their dedicated viewers). SVG
// stays with the schematic viewer; only raster images route to `image:`.
const IMAGE_EXT = /\.(png|jpe?g|webp|gif)$/;
const DATA_EXT = /\.(csv|tsv|json|ya?ml)$/;
const TEXT_EXT = /\.(txt|log|rpt)$/;

export function artifactKeyForFile(path: string): ArtifactKey {
  const runId = runIdFromPath(path);
  const lower = path.toLowerCase();
  // A run's VCD shares the run-scoped tab; any other VCD still gets the
  // waveform viewer via the path-backed key (never Monaco-as-text).
  if (lower.endsWith(".vcd")) return runId ? `wave:${runId}` : `wavefile:${path}`;
  if (lower.endsWith(".gds") && runId) return `layout:${runId}`;
  if (lower.endsWith(".md") && runId) return `report:${runId}`;
  if (lower.endsWith(".svg") && !lower.endsWith(".gds.svg") && !runId) {
    return `schematic:${path}`;
  }
  if (/(^|\/)[^/]*_spec\.yaml$/.test(lower)) return "spec";
  if (IMAGE_EXT.test(lower)) return `image:${path}`;
  if (DATA_EXT.test(lower)) return `data:${path}`;
  if (TEXT_EXT.test(lower)) return `text:${path}`;
  return `code:${path}`;
}

const KIND_LABEL: Record<string, string> = {
  code: "Code",
  spec: "Spec",
  wave: "Waveform",
  wavefile: "Waveform",
  report: "Report",
  layout: "Layout",
  schematic: "Schematic",
  image: "Image",
  data: "Data",
  text: "Text",
};

// File-path-backed kinds label by basename (like code); run-scoped kinds label
// by "<Kind> · <ref>".
const BASENAME_KINDS = new Set(["code", "schematic", "image", "data", "text", "wavefile"]);

/** Short human label for a tab / quick-open row. */
export function artifactLabel(key: ArtifactKey): string {
  const parsed = parseArtifactKey(key);
  if (!parsed) return key;
  if (parsed.kind === "spec") return "Spec";
  if (BASENAME_KINDS.has(parsed.kind)) {
    const ref = parsed.ref ?? "";
    return ref.split("/").pop() || ref || KIND_LABEL[parsed.kind];
  }
  return `${KIND_LABEL[parsed.kind]} · ${parsed.ref}`;
}
