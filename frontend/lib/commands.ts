import { workbenchApi } from "@/lib/api";
import { toSynthJobStatus, useStore } from "@/lib/store";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import type { ActivityEvent, DesignManifest, RunSummary } from "@/types";

// The v2 invocation model: every tool run — palette (⌘K), file context menu,
// activity "Re-run", param modal — goes through this registry. The guiding
// principle: THE MANIFEST SUPPLIES FILES AND TARGETS; THE USER ONLY SUPPLIES
// CHOICES. Files are never hand-picked in the UI — the backend re-resolves
// each command's file set from the manifest (files_for_stage), so the param
// surface here is choices only (platform, clock, mode, stages…).
//
// Sync commands (lint, sim) resolve inline; async ones (synth, pnr) dispatch a
// job and poll honestly. Nothing here auto-switches the artifact center: a
// finished run marks itself unread in the Runs panel instead (v2 principle:
// no view hijacking).

export type CommandId = "lint" | "sim" | "synth" | "pnr";

export const RUN_ORDER: CommandId[] = ["lint", "sim", "synth", "pnr"];

export const PLATFORMS = ["sky130hd", "sky130hs", "nangate45", "asap7", "gf180", "ihp-sg13g2"] as const;

// ORFS PD stage sequence (synthesis_manager.PD_STAGE_SEQUENCE minus the two
// non-retryable prep stages — retries restart from a physical-design stage).
export const PD_STAGES = ["floorplan", "place", "cts", "grt", "route", "finish"] as const;

// Full stage bound for start_synthesis' maxStage — "synth" is the fast
// synthesis-only PPA estimate; "finish" is the full RTL→GDS flow.
export const SYNTH_STAGES = ["synth", "floorplan", "place", "cts", "grt", "route", "finish"] as const;

// Lint engines (POST /lint body) — auto resolves server-side to verilator
// when installed, else iverilog.
export const LINT_ENGINES = ["auto", "iverilog", "verilator"] as const;

/** Testbench-module choices for the sim combobox: the manifest's derived
 *  `testbenches` list, falling back to the single simTop on legacy manifests. */
export function testbenchChoices(manifest: DesignManifest | null): string[] {
  const modules = Array.from(new Set((manifest?.testbenches ?? []).map((t) => t.module)));
  if (modules.length > 0) return modules;
  return manifest?.simTop ? [manifest.simTop] : [];
}

export interface CommandParam {
  key: string;
  label: string;
  /** "combo" = text input with filtered suggestions; free entry always allowed. */
  type: "enum" | "number" | "boolean" | "text" | "combo";
  options?: readonly string[];
  unit?: string;
  step?: number;
  min?: number;
  advanced?: boolean;
  hint?: string;
  /** Where the default comes from — drives the source badge in the modal. */
  source: "manifest" | "choice" | "run" | "default";
}

export interface CommandDef {
  id: CommandId;
  label: string;
  /** Real backend tool name — matches what the agent calls and what the
   *  activity log records, so feed rows and palette entries speak one language. */
  tool: string;
  description: string;
  async: boolean;
  /** Display shortcut, rendered as ⌘/Ctrl + key. */
  shortcut: string;
  params: CommandParam[];
}

export const COMMANDS: Record<CommandId, CommandDef> = {
  lint: {
    id: "lint",
    label: "Lint",
    tool: "linter_tool",
    description: "Lint the design sources (rtl + includes from the manifest).",
    async: false,
    shortcut: "L",
    params: [
      { key: "engine", label: "Engine", type: "enum", options: LINT_ENGINES, source: "choice" },
    ],
  },
  sim: {
    id: "sim",
    label: "Simulate",
    tool: "run_isolated_simulation",
    description: "Run the testbench in an isolated run directory; captures a waveform.",
    async: false,
    shortcut: "R",
    params: [
      { key: "mode", label: "Mode", type: "enum", options: ["rtl", "post_synth"], source: "choice" },
      // Options resolve live from manifest.testbenches (see CommandModal's
      // optionsFor) — free entry stays allowed for modules the scan missed.
      { key: "simTop", label: "Testbench", type: "combo", source: "manifest", hint: "which testbench to run" },
    ],
  },
  synth: {
    id: "synth",
    label: "Synthesize",
    tool: "start_synthesis",
    description: "Dispatch an OpenROAD-flow synthesis + PD job for the synth top.",
    async: true,
    shortcut: "Y",
    params: [
      { key: "platform", label: "Platform", type: "enum", options: PLATFORMS, source: "manifest" },
      { key: "maxStage", label: "Max stage", type: "enum", options: SYNTH_STAGES, source: "choice", hint: "“synth” = fast synthesis-only estimate" },
      { key: "clockPeriodNs", label: "Clock period", type: "number", unit: "ns", step: 0.1, min: 0.1, source: "manifest" },
      { key: "utilization", label: "Utilization", type: "number", unit: "%", step: 1, min: 1, advanced: true, source: "default" },
      { key: "aspectRatio", label: "Aspect ratio", type: "number", step: 0.1, min: 0.1, advanced: true, source: "default" },
      { key: "coreMargin", label: "Core margin", type: "number", unit: "µm", step: 0.5, min: 0, advanced: true, source: "default" },
      { key: "runEquiv", label: "Equivalence check", type: "boolean", advanced: true, source: "default" },
    ],
  },
  pnr: {
    id: "pnr",
    label: "Retry P&R",
    tool: "retry_pd",
    description: "Re-run physical design from a chosen stage of an existing synth run.",
    async: true,
    shortcut: "E",
    params: [
      { key: "runId", label: "Source run", type: "enum", options: [], source: "run" },
      { key: "fromStage", label: "From stage", type: "enum", options: PD_STAGES, source: "choice" },
      { key: "maxStage", label: "To stage", type: "enum", options: PD_STAGES, source: "choice" },
    ],
  },
};

export type CommandValues = Record<string, unknown>;

/** Latest synth runs, newest first — the pnr command's source-run choices. */
export function synthRunChoices(runs: RunSummary[]): string[] {
  return runs.filter((r) => r.kind === "synth").map((r) => r.id);
}

/** Per-command defaults, resolved from live state (manifest, runs). */
export function defaultValues(
  id: CommandId,
  ctx: { manifest: DesignManifest | null; runs: RunSummary[] }
): CommandValues {
  switch (id) {
    case "lint":
      return { engine: "auto" };
    case "sim":
      return { mode: "rtl", simTop: ctx.manifest?.simTop ?? "" };
    case "synth":
      return {
        platform: ctx.manifest?.platform ?? "sky130hd",
        maxStage: "finish",
        clockPeriodNs: ctx.manifest?.clockPeriodNs ?? 10,
        utilization: 5,
        aspectRatio: 1.0,
        coreMargin: 2.0,
        runEquiv: false,
      };
    case "pnr":
      return {
        runId: synthRunChoices(ctx.runs)[0] ?? "",
        fromStage: "floorplan",
        maxStage: "finish",
      };
  }
}

// Mirror of the backend's files_for_stage (src/tools/manifest.py) — used ONLY
// for the modal's "Supplied by manifest" display; the backend re-resolves the
// real set at execution time, so this can never drift into behavior.
const STAGE_ROLES: Record<string, string[]> = {
  lint: ["rtl", "include"],
  sim: ["rtl", "tb", "include"],
  synth: ["rtl", "sdc"],
  pnr: [],
};

export interface ManifestFact {
  label: string;
  value: string;
}

/** The "Supplied by manifest" facts shown in the param modal. */
export function manifestFacts(
  id: CommandId,
  ctx: { manifest: DesignManifest | null }
): ManifestFact[] {
  const m = ctx.manifest;
  if (!m) return [];
  const files = (roles: string[]) =>
    m.files.filter((f) => roles.includes(f.role)).map((f) => f.name);
  switch (id) {
    case "lint":
      return [{ label: "files", value: files(STAGE_ROLES.lint).join(", ") || "—" }];
    case "sim":
      return [
        { label: "default tb", value: m.simTop || "—" },
        { label: "testbenches", value: `${testbenchChoices(m).length} available` },
        { label: "files", value: files(STAGE_ROLES.sim).join(", ") || "—" },
      ];
    case "synth":
      return [
        { label: "top module", value: m.synthTop ?? "—" },
        { label: "sources", value: files(["rtl"]).join(", ") || "—" },
        { label: "constraints", value: files(["sdc"]).join(", ") || "auto" },
      ];
    case "pnr":
      return [{ label: "reuses", value: "netlist + constraints of the source run" }];
  }
}

/** Map an activity-feed tool name back to its command (for "Re-run"). */
export function commandForTool(tool: string): CommandId | null {
  switch (tool) {
    case "linter_tool":
      return "lint";
    case "run_isolated_simulation":
    case "simulation_tool":
      return "sim";
    case "start_synthesis":
      return "synth";
    case "retry_pd":
      return "pnr";
    default:
      return null;
  }
}

// --- Execution ---------------------------------------------------------------

let localSeq = 0;
function localEvent(tool: string, args: Record<string, unknown>): ActivityEvent {
  return {
    id: `local:${Date.now()}-${localSeq++}`,
    ts: new Date().toISOString(),
    source: "user",
    tool,
    args,
    status: "running",
    resultSummary: "",
    durationMs: null,
    runId: null,
    threadId: null,
  };
}

function errText(e: unknown): string {
  if (e instanceof Error) return e.message;
  return String(e);
}

const JOB_DEADLINE_MS = 20 * 60 * 1000;

/** Poll an async job to a terminal state, honestly and politely.
 *  Respects the backend's own poll_after_sec hint when present. */
async function pollJob(
  sessionId: string,
  jobId: string,
  runId: string
): Promise<Record<string, unknown> | null> {
  const store = useStore.getState;
  const deadline = Date.now() + JOB_DEADLINE_MS;
  let interval = 3000;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, interval));
    if (store().currentSession?.id !== sessionId) {
      useStore.setState({ synthJob: null });
      return null; // switched away
    }
    let job: Record<string, unknown>;
    try {
      job = await workbenchApi.getJob(sessionId, jobId);
    } catch {
      interval = Math.min(interval * 1.5, 30000);
      continue;
    }
    const state = String(job.status ?? "");
    if (state === "completed" || state === "failed") {
      useStore.setState({ synthJob: null });
      return job;
    }
    // Publish the live stage for anything rendering run state (RunsPane shows
    // the current PD stage next to the RUNNING synth run).
    useStore.setState({ synthJob: toSynthJobStatus(jobId, runId, job) });
    const hint = Number(job.poll_after_sec);
    interval = Number.isFinite(hint) && hint > 0
      ? Math.min(hint * 1000, 60000)
      : Math.min(interval * 1.5, 30000);
    void store().loadRuns();
  }
  useStore.setState({ synthJob: null });
  return { status: "failed", timeout: true };
}

/**
 * Run a command. `values` omitted → manifest-derived defaults (the ⌘K fast
 * path); the param modal passes explicit values. Results surface through the
 * Activity feed + Runs panel (+ a toast); the artifact center is never
 * auto-switched — completed runs get an unread marker instead.
 */
// Double-submit guard: a rapid second ⌘L/⌘R while the first is in flight is
// a no-op. Sync commands hold the guard for their whole call; async ones only
// through dispatch (queuing a second synth job behind a running one is valid).
const inFlight = new Set<CommandId>();

export async function runCommand(id: CommandId, values?: CommandValues): Promise<void> {
  const store = useStore.getState();
  const session = store.currentSession;
  if (!session) return;
  if (inFlight.has(id)) return;
  inFlight.add(id);
  const sessionId = session.id;
  const ui = useWorkbenchUiStore.getState();
  const cmd = COMMANDS[id];
  const vals = { ...defaultValues(id, { manifest: store.manifest, runs: store.runs }), ...(values ?? {}) };

  const ev = localEvent(cmd.tool, vals);
  store.appendLocalActivity(ev);
  const done = (patch: Partial<ActivityEvent>) =>
    useStore.getState().appendLocalActivity({
      ...ev,
      durationMs: Date.now() - new Date(ev.ts).getTime(),
      ...patch,
    });
  const refresh = () => {
    const s = useStore.getState();
    void s.loadActivity();
    void s.loadRuns();
  };

  try {
    switch (id) {
      case "lint": {
        const result = await workbenchApi.lint(sessionId, {
          engine: String(vals.engine ?? "auto"),
        });
        const nErr = result.errors.length;
        const nWarn = result.warnings.length;
        // Auto resolves server-side — name the engine that actually ran.
        const engineTag = result.engine ? ` (${result.engine})` : "";
        done({
          status: result.status === "passed" ? "ok" : "error",
          resultSummary: `${result.status}${engineTag} · ${nErr} error(s), ${nWarn} warning(s)`,
        });
        store.pushToast(
          result.status === "passed"
            ? { kind: nWarn ? "info" : "success", title: `Lint passed${engineTag}${nWarn ? ` · ${nWarn} warning(s)` : ""}` }
            : { kind: "error", title: `Lint failed${engineTag} · ${nErr} error(s)` }
        );
        // Keep the structured diagnostics available to the feed/editor.
        useStore.setState({ lintResult: result });
        break;
      }

      case "sim": {
        const simTop = String(vals.simTop ?? "").trim();
        const run = await workbenchApi.simulate(sessionId, {
          mode: String(vals.mode ?? "rtl"),
          // Empty = let the backend fall back to the manifest's default TB.
          ...(simTop ? { simTop } : {}),
        });
        done({
          status: run.status === "passed" ? "ok" : "error",
          runId: run.id,
          resultSummary:
            run.status === "passed"
              ? `${run.id} passed`
              : `${run.id} failed${run.failure?.timeNs != null ? ` @ ${run.failure.timeNs}ns` : ""}`,
        });
        ui.markUnread(sessionId, run.id);
        store.pushToast(
          run.status === "passed"
            ? { kind: "success", title: "Simulation passed", detail: run.id }
            : {
                kind: "error",
                title: `Simulation failed${run.failure?.timeNs != null ? ` @ ${run.failure.timeNs}ns` : ""}`,
                detail: [run.id, run.failure?.firstFailureLine].filter(Boolean).join(" — ") || undefined,
              }
        );
        break;
      }

      case "synth":
      case "pnr": {
        if (id === "pnr" && !vals.runId) {
          done({ status: "error", resultSummary: "No synth run to retry from" });
          store.pushToast({ kind: "error", title: "P&R retry needs a source synth run" });
          break;
        }
        const dispatch =
          id === "synth"
            ? await workbenchApi.synthesize(sessionId, {
                platform: vals.platform,
                maxStage: String(vals.maxStage ?? "finish"),
                clockPeriodNs: vals.clockPeriodNs,
                utilization: vals.utilization,
                aspectRatio: vals.aspectRatio,
                coreMargin: vals.coreMargin,
                runEquiv: vals.runEquiv,
              })
            : await workbenchApi.retryRun(sessionId, String(vals.runId), {
                fromStage: String(vals.fromStage ?? "floorplan"),
                maxStage: String(vals.maxStage ?? "finish"),
              });
        const { jobId, runId } = dispatch;
        inFlight.delete(id); // dispatched — a second job may now be queued
        done({ runId, resultSummary: `${runId} dispatched (job ${jobId})` });
        store.pushToast({ kind: "info", title: id === "synth" ? "Synthesis dispatched" : "P&R retry dispatched", detail: runId });
        refresh();

        const job = await pollJob(sessionId, jobId, runId);
        if (!job) return; // session switched — stop narrating
        const okDone = String(job.status) === "completed";
        done({
          status: okDone ? "ok" : "error",
          runId,
          resultSummary: okDone ? `${runId} completed` : `${runId} failed`,
        });
        useWorkbenchUiStore.getState().markUnread(sessionId, runId);
        if (okDone) {
          await useStore.getState().refreshSynthArtifacts?.(runId);
          useStore.getState().pushToast({ kind: "success", title: "Synthesis completed", detail: runId });
        } else {
          const notes = typeof job.check_notes === "string" ? job.check_notes : "";
          useStore.getState().pushToast({
            kind: "error",
            title: id === "synth" ? "Synthesis failed" : "P&R retry failed",
            detail: [runId, notes].filter(Boolean).join(" — ") || undefined,
          });
        }
        // A finished run's artifacts now exist on disk — refresh the tree.
        useStore.getState().invalidateDirs(["", "synth_runs"]);
        break;
      }
    }
  } catch (e) {
    done({ status: "error", resultSummary: errText(e) });
    store.pushToast({ kind: "error", title: `${cmd.label} failed`, detail: errText(e) });
  } finally {
    inFlight.delete(id);
    refresh();
  }
}
