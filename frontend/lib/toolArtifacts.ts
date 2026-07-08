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
 * Map a tool call (+ its result text) to the ArtifactKey it produced.
 *
 *   write_file / edit_file_tool / apply_patch_tool → code:<file>
 *   write_spec / read_spec / load_yaml_spec_file   → spec
 *   simulation_tool / run_isolated_simulation      → wave:<runId from result>
 *   start_synthesis / retry_pd / get_synthesis_metrics /
 *   read_stage_report / generate_report_tool       → report:<runId from args|result>
 *   schematic_tool                                 → schematic:<svg name> (if extractable)
 *   waveform_tool                                  → wave:<runId> (vcd_file in a run dir)
 *
 * Everything else (and any family missing its ref) → null.
 */
export function artifactKeyForToolCall(
  toolName: string,
  args: Record<string, unknown>,
  resultText?: string | null
): ArtifactKey | null {
  switch (toolName) {
    case "write_file":
    case "edit_file_tool": {
      const file = firstStringArg(args, ["filename", "target_file", "file", "path"]);
      return file ? `code:${file}` : null;
    }

    case "apply_patch_tool": {
      const file =
        firstStringArg(args, ["filename", "target_file"]) ??
        fileFromUnifiedDiff(str(args.unified_diff));
      return file ? `code:${file}` : null;
    }

    case "write_spec":
    case "read_spec":
    case "load_yaml_spec_file":
      return "spec";

    case "simulation_tool":
    case "run_isolated_simulation": {
      const runId = runIdFromText(resultText);
      return runId ? `wave:${runId}` : null;
    }

    case "start_synthesis":
    case "retry_pd":
    case "get_synthesis_metrics":
    case "read_stage_report":
    case "generate_report_tool": {
      const runId =
        runIdFromText(str(args.run_id)) ?? runIdFromText(resultText);
      return runId ? `report:${runId}` : null;
    }

    case "schematic_tool": {
      const svg =
        SVG_RE.exec(str(args.output_file) ?? "")?.[0] ??
        SVG_RE.exec(resultText ?? "")?.[0] ??
        null;
      return svg ? `schematic:${svg}` : null;
    }

    case "waveform_tool": {
      // Run-scoped VCDs share the run's tab; any other VCD opens by path —
      // the path-backed key is exact, so no run attribution is guessed.
      const vcd = str(args.vcd_file);
      if (!vcd) return null;
      const runId = runIdFromPath(vcd);
      return runId ? `wave:${runId}` : `wavefile:${vcd}`;
    }

    case "run_python_analysis":
      return pythonAnalysisArtifactKey(args, resultText);

    default:
      return null;
  }
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
