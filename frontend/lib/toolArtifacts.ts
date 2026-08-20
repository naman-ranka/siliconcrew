import type { ArtifactKey } from "@/lib/artifactKeys";
import { runIdFromPath } from "@/lib/openArtifact";
import type { ActivityEvent } from "@/types";

// Pure mapping: a finished tool call → the artifact it produced/touched (S5-1).
// Used by ToolCallCard ("Open <kind> →") and the inline action cards. Returns
// null whenever the mapping would be a guess — the button simply doesn't
// render; nothing opens on its own.

/** Run-id naming convention shared with the activity feed / run dirs:
 *  sim_0001, synth_0042, … (same `(sim|synth)_\d+` shape as
 *  openArtifact.runIdFromPath uses for run directories). */
export const RUN_ID_RE = /\b(?:sim|synth)_\d+\b/;

/** First run id mentioned in a blob of text (tool result, summary…). */
export function runIdFromText(text: string | null | undefined): string | null {
  if (!text) return null;
  return RUN_ID_RE.exec(text)?.[0] ?? null;
}

function str(v: unknown): string | null {
  return typeof v === "string" && v.length > 0 ? v : null;
}

function firstStringArg(args: Record<string, unknown>, keys: string[]): string | null {
  for (const k of keys) {
    const v = str(args[k]);
    if (v) return v;
  }
  return null;
}

/** `+++ b/foo.v` (or `+++ foo.v`) target of a unified diff — apply_patch_tool
 *  carries no filename arg, only the diff itself. */
function fileFromUnifiedDiff(diff: string | null): string | null {
  if (!diff) return null;
  const m = /^\+\+\+\s+(?:b\/)?(\S+)/m.exec(diff);
  if (!m) return null;
  // "/dev/null" means the diff deletes the file — nothing to open.
  return m[1] === "/dev/null" ? null : m[1];
}

const SVG_RE = /\b[\w./-]+\.svg\b/;

/** One key per file for EVERY mutation tool (write/edit/patch must agree, or
 *  the same file opens under two tab keys — the dual-key class of bug
 *  migrateVcdTabKey exists for). Dashboards open in the interactive viewer
 *  (the sim is the point); everything else written opens as code. */
function mutationKey(file: string): ArtifactKey {
  return file.toLowerCase().endsWith(".dashboard.html")
    ? `interactive:${file}`
    : `code:${file}`;
}

/** One produced artifact from a `run_python_analysis` result payload. */
interface PyArtifact {
  path: string;
  kind: string;
  bytes?: number;
}

/**
 * `run_python_analysis` returns `{…, artifacts: [{path, kind, bytes}]}` where
 * kind ∈ image|data|text|vector|file. The card opens ONE primary artifact
 * (multi-artifact cards are deferred, PA9): the first with a rich viewer
 * (image → data → text), else the input script so there is always something to
 * open. Parses defensively — a non-JSON or shapeless result yields the script
 * fallback / null.
 */
function pythonAnalysisArtifactKey(
  args: Record<string, unknown>,
  resultText?: string | null
): ArtifactKey | null {
  let artifacts: PyArtifact[] = [];
  if (resultText) {
    try {
      const parsed = JSON.parse(resultText) as { artifacts?: unknown };
      if (Array.isArray(parsed.artifacts)) {
        artifacts = parsed.artifacts.filter(
          (a): a is PyArtifact =>
            !!a && typeof (a as PyArtifact).path === "string" && typeof (a as PyArtifact).kind === "string"
        );
      }
    } catch {
      // Not JSON (or truncated) — fall through to the script fallback.
    }
  }
  const pick = (kind: string) => artifacts.find((a) => a.kind === kind);
  const primary = pick("image") ?? pick("data") ?? pick("text");
  if (primary) return `${primary.kind}:${primary.path}`;
  // vector/file artifacts have no rich viewer → open the input script instead.
  const script = firstStringArg(args, ["script_file"]);
  return script ? `code:${script}` : null;
}

/**
 * Which artifact a finished tool call produced, per tool. This is the one map
 * the catalog cannot supply: it is arg-and-result shaped, not policy — only
 * this file knows that `waveform_tool`'s `vcd_file` names a run's waveform.
 *
 * NOT total, by design: a tool with no entry (and any entry that cannot find
 * its reference) yields null and the "Open …" button simply does not render —
 * an honest absence, never a guess. What IS enforced by
 * test/toolRegistry.coverage.test.ts is that every key here is still a live
 * tool, so a renamed or merged tool takes the button down loudly.
 *
 *   write_file / edit_file_tool / apply_patch_tool → code:<file>
 *   write_spec / read_spec / load_yaml_spec_file   → spec
 *   simulation_tool / run_isolated_simulation      → wave:<runId from result>
 *   start_synthesis / retry_pd / get_synthesis_metrics /
 *   read_stage_report / generate_report_tool       → report:<runId from args|result>
 *   schematic_tool                                 → schematic:<svg name> (if extractable)
 *   waveform_tool                                  → wave:<runId> (vcd_file in a run dir)
 */
type ArtifactResolver = (
  args: Record<string, unknown>,
  resultText?: string | null
) => ArtifactKey | null;

const mutationArtifact: ArtifactResolver = (args) => {
  const file = firstStringArg(args, ["filename", "target_file", "file", "path"]);
  return file ? mutationKey(file) : null;
};

const specArtifact: ArtifactResolver = () => "spec";

const simArtifact: ArtifactResolver = (_args, resultText) => {
  const runId = runIdFromText(resultText);
  return runId ? `wave:${runId}` : null;
};

const reportArtifact: ArtifactResolver = (args, resultText) => {
  const runId = runIdFromText(str(args.run_id)) ?? runIdFromText(resultText);
  return runId ? `report:${runId}` : null;
};

export const TOOL_ARTIFACT_RESOLVERS: Readonly<Record<string, ArtifactResolver>> = {
  write_file: mutationArtifact,
  edit_file_tool: mutationArtifact,

  apply_patch_tool: (args) => {
    const file =
      firstStringArg(args, ["filename", "target_file"]) ??
      fileFromUnifiedDiff(str(args.unified_diff));
    return file ? mutationKey(file) : null;
  },

  write_spec: specArtifact,
  read_spec: specArtifact,
  load_yaml_spec_file: specArtifact,

  simulation_tool: simArtifact,
  run_isolated_simulation: simArtifact,

  start_synthesis: reportArtifact,
  retry_pd: reportArtifact,
  get_synthesis_metrics: reportArtifact,
  read_stage_report: reportArtifact,
  generate_report_tool: reportArtifact,

  schematic_tool: (args, resultText) => {
    const svg =
      SVG_RE.exec(str(args.output_file) ?? "")?.[0] ??
      SVG_RE.exec(resultText ?? "")?.[0] ??
      null;
    return svg ? `schematic:${svg}` : null;
  },

  waveform_tool: (args) => {
    // Run-scoped VCDs share the run's tab; any other VCD opens by path —
    // the path-backed key is exact, so no run attribution is guessed.
    const vcd = str(args.vcd_file);
    if (!vcd) return null;
    const runId = runIdFromPath(vcd);
    return runId ? `wave:${runId}` : `wavefile:${vcd}`;
  },

  build_interactive_sim: (args) => {
    // The openable thing at build time is the websim artifact itself (the
    // dashboard usually doesn't exist yet); it's JSON → data viewer. The
    // artifact name is deterministic from the tool's own arg — never
    // scraped from result prose.
    const top = firstStringArg(args, ["top_module"]);
    return top ? `data:${top}.websim.json` : null;
  },

  run_python_analysis: pythonAnalysisArtifactKey,
};

/** Map a tool call (+ its result text) to the ArtifactKey it produced. */
export function artifactKeyForToolCall(
  toolName: string,
  args: Record<string, unknown>,
  resultText?: string | null
): ArtifactKey | null {
  return TOOL_ARTIFACT_RESOLVERS[toolName]?.(args, resultText) ?? null;
}

/** Same mapping for an activity event — the event's structured runId (when the
 *  backend already extracted one) beats re-parsing the summary text. */
export function artifactKeyForActivity(
  event: Pick<ActivityEvent, "tool" | "args" | "resultSummary" | "runId">
): ArtifactKey | null {
  // Structured runId FIRST: the regex takes the first match, and a summary
  // like "regressed vs synth_0001" must not beat the event's own run id.
  const hint = event.runId
    ? `${event.runId} ${event.resultSummary ?? ""}`
    : event.resultSummary;
  return artifactKeyForToolCall(event.tool, event.args ?? {}, hint);
}
