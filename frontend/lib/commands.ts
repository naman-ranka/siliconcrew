import { workbenchApi } from "@/lib/api";
import { useStore } from "@/lib/store";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import type { ActivityEvent, DesignManifest, RunSummary } from "@/types";

// The v2 invocation model: every tool run — palette (⌘K), file context menu,
// activity "Re-run", param modal — goes through this registry. The guiding
// principle: THE MANIFEST SUPPLIES FILES AND TARGETS; THE USER ONLY SUPPLIES
// CHOICES. Files are never hand-picked in the UI — the backend re-resolves
// each command's file set from the manifest (files_for_stage), so the param
// surface here is choices only (platform, clock, mode, stages…).
//
// Sync commands (lint, sim) resolve inline; async ones (synth, pnr) are
// DISPATCH-ONLY: POST → run appears queued/running → done. The UI is a viewer
// of the event log — it never polls run status. Completion arrives through
// activity events, a user Refresh, or focus revalidate, and the store's
// runs-slice transition detector owns unread marking, toasts and artifact
// refresh. Nothing here auto-switches the artifact center (v2 principle: no
// view hijacking).

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

/** Live state every default / option / manifest fact resolves against. */
export interface CommandCtx {
  manifest: DesignManifest | null;
  runs: RunSummary[];
}

export interface CommandParam {
  key: string;
  label: string;
  /** "combo" = text input with filtered suggestions; free entry always allowed. */
  type: "enum" | "number" | "boolean" | "text" | "combo";
  /** Fixed choices, or a resolver against live state (testbenches, runs). */
  options?: readonly string[] | ((ctx: CommandCtx) => string[]);
  /** The parameter's default — one declaration, read by BOTH surfaces. */
  def: unknown | ((ctx: CommandCtx) => unknown);
  unit?: string;
  step?: number;
  min?: number;
  max?: number;
  advanced?: boolean;
  hint?: string;
  /** Empty value is dropped from the payload (backend falls back). */
  optional?: boolean;
  /** Where the default comes from — drives the source badge in the modal. */
  source: "manifest" | "choice" | "run" | "default";
}

export interface ManifestFact {
  label: string;
  value: string;
}

export interface CommandDef {
  id: CommandId;
  label: string;
  /** Real backend tool name — matches what the agent calls and what the
   *  activity log records, so feed rows and palette entries speak one language. */
  tool: string;
  /** Other tool names whose activity events belong to this command (the older
   *  agent-side twin of the same flow step). */
  alsoTools?: readonly string[];
  description: string;
  async: boolean;
  /** Display shortcut, rendered as ⌘/Ctrl + key. */
  shortcut: string;
  /** "Supplied by manifest" — shown in both the param modal and the Command
   *  Surface, so the two can never tell the user different stories. */
  facts?: (ctx: CommandCtx) => ManifestFact[];
  params: CommandParam[];
}

const filesByRole = (m: DesignManifest | null, roles: string[]): string =>
  (m?.files ?? []).filter((f) => roles.includes(f.role)).map((f) => f.name).join(", ") || "—";

/**
 * The four core flow commands — the ONE definition of them in the frontend.
 * They stay hand-written (unlike every other tool, which the Command Surface
 * renders straight from the catalog) because they mirror REST request bodies,
 * which ARE their contract, and dispatch through runCommand below. The Command
 * Surface derives its own view of these from here (lib/commandSurface.ts);
 * there is no second copy to keep in sync.
 *
 * THE MANIFEST SUPPLIES FILES AND TARGETS; THE USER ONLY SUPPLIES CHOICES.
 */
export const COMMANDS: Record<CommandId, CommandDef> = {
  lint: {
    id: "lint",
    label: "Lint",
    tool: "linter_tool",
    description:
      "Lint/syntax check (iverilog or verilator). The manifest supplies the rtl + include files.",
    async: false,
    shortcut: "L",
    facts: (c: CommandCtx) => [{ label: "files", value: filesByRole(c.manifest, ["rtl", "include"]) }],
    params: [
      { key: "engine", label: "Engine", type: "enum", options: LINT_ENGINES, def: "auto", source: "choice" },
    ],
  },
  sim: {
    id: "sim",
    label: "Simulate",
    tool: "run_isolated_simulation",
    alsoTools: ["simulation_tool"],
    description:
      "Manifest-driven sim in its own sim_runs/sim_NNNN/ dir — own VCD + provenance.",
    async: false,
    shortcut: "R",
    facts: (c: CommandCtx) => [
      { label: "default tb", value: c.manifest?.simTop || "—" },
      { label: "testbenches", value: `${testbenchChoices(c.manifest).length} available` },
      { label: "files", value: filesByRole(c.manifest, ["rtl", "tb", "include"]) },
    ],
    params: [
      { key: "mode", label: "Mode", type: "enum", options: ["rtl", "post_synth"], def: "rtl", source: "choice" },
      // Options resolve live from manifest.testbenches — free entry stays
      // allowed for modules the scan missed.
      {
        key: "simTop", label: "Testbench", type: "combo", source: "manifest",
        options: (c) => testbenchChoices(c.manifest),
        def: (c: CommandCtx) => c.manifest?.simTop ?? "",
        optional: true, // empty → backend falls back to the manifest default
        hint: "which testbench to run",
      },
    ],
  },
  synth: {
    id: "synth",
    label: "Synthesize",
    tool: "start_synthesis",
    description:
      "Async ORFS job for the synth top → { run_id } immediately; completion arrives via activity events / Refresh (no client polling).",
    async: true,
    shortcut: "Y",
    facts: (c: CommandCtx) => [
      { label: "top module", value: c.manifest?.synthTop ?? "—" },
      { label: "sources", value: filesByRole(c.manifest, ["rtl"]) },
      { label: "constraints", value: (c.manifest?.files ?? []).some((f) => f.role === "sdc") ? filesByRole(c.manifest, ["sdc"]) : "auto" },
    ],
    params: [
      { key: "platform", label: "Platform", type: "enum", options: PLATFORMS, def: (c: CommandCtx) => c.manifest?.platform ?? "sky130hd", source: "manifest" },
      { key: "maxStage", label: "Max stage", type: "enum", options: SYNTH_STAGES, def: "finish", source: "choice", hint: "“synth” = fast synthesis-only estimate" },
      { key: "clockPeriodNs", label: "Clock period", type: "number", unit: "ns", step: 0.1, min: 0.1, def: (c: CommandCtx) => c.manifest?.clockPeriodNs ?? 10, source: "manifest" },
      { key: "utilization", label: "Utilization", type: "number", unit: "%", step: 1, min: 1, max: 100, def: 40, advanced: true, source: "default" },
      { key: "aspectRatio", label: "Aspect ratio", type: "number", step: 0.1, min: 0.1, def: 1.0, advanced: true, source: "default" },
      { key: "coreMargin", label: "Core margin", type: "number", unit: "µm", step: 0.5, min: 0, def: 2.0, advanced: true, source: "default" },
      { key: "runEquiv", label: "Equivalence check", type: "boolean", def: false, advanced: true, source: "default" },
    ],
  },
  pnr: {
    id: "pnr",
    label: "Retry P&R",
    tool: "retry_pd",
    description:
      "Branches a child PD run from an existing run and reruns downstream ORFS stages — first-class lineage.",
    async: true,
    shortcut: "E",
    facts: () => [{ label: "reuses", value: "netlist + constraints of the source run" }],
    params: [
      {
        key: "runId", label: "Source run", type: "enum", source: "run",
        options: (c) => synthRunChoices(c.runs),
        def: (c: CommandCtx) => synthRunChoices(c.runs)[0] ?? "",
        hint: "parent run to branch from",
      },
      { key: "fromStage", label: "From stage", type: "enum", options: PD_STAGES, def: "floorplan", source: "choice" },
      { key: "maxStage", label: "To stage", type: "enum", options: PD_STAGES, def: "finish", source: "choice" },
    ],
  },
};

export type CommandValues = Record<string, unknown>;

/** Latest synth runs, newest first — the pnr command's source-run choices. */
export function synthRunChoices(runs: RunSummary[]): string[] {
  return runs.filter((r) => r.kind === "synth").map((r) => r.id);
}

/** A param's default, resolved against live state. */
export function resolveParamDef(p: CommandParam, ctx: CommandCtx): unknown {
  return typeof p.def === "function" ? (p.def as (c: CommandCtx) => unknown)(ctx) : p.def;
}

/** A param's choices, resolved against live state. */
export function resolveParamOptions(p: CommandParam, ctx: CommandCtx): string[] {
  if (!p.options) return [];
  return typeof p.options === "function" ? p.options(ctx) : [...p.options];
}

/** Per-command defaults, resolved from live state (manifest, runs). */
export function defaultValues(id: CommandId, ctx: CommandCtx): CommandValues {
  const out: CommandValues = {};
  for (const p of COMMANDS[id].params) out[p.key] = resolveParamDef(p, ctx);
  return out;
}

/** The "Supplied by manifest" facts — the backend re-resolves the real file
 *  set at execution time, so these can never drift into behavior. */
export function manifestFacts(id: CommandId, ctx: { manifest: DesignManifest | null }): ManifestFact[] {
  if (!ctx.manifest) return [];
  return COMMANDS[id].facts?.({ manifest: ctx.manifest, runs: [] }) ?? [];
}

/**
 * Values for running a command FROM a specific file (the explorer's context
 * menu) — dev#51 (2): right-click → Simulate on a testbench must run THAT
 * testbench, not silently fall back to the manifest default.
 *
 * Only mappings the REST contracts can honestly express are made: sim gets
 * `simTop` when the clicked file is a known testbench (manifest.testbenches
 * carries file → module). Lint/synth bodies have no per-file field — the
 * backend re-resolves their sets from the manifest — so they pass nothing
 * rather than a pretend argument the backend would ignore.
 */
export function commandValuesForFile(
  id: CommandId,
  path: string,
  manifest: DesignManifest | null
): CommandValues {
  if (id === "sim") {
    const tb = (manifest?.testbenches ?? []).find((t) => t.file === path);
    if (tb?.module) return { simTop: tb.module };
  }
  return {};
}

/** Map an activity-feed tool name back to its command (for "Re-run") — read
 *  off the registry above, so a renamed tool cannot leave a dead branch here. */
export function commandForTool(tool: string): CommandId | null {
  for (const id of RUN_ORDER) {
    const def = COMMANDS[id];
    if (def.tool === tool || def.alsoTools?.includes(tool)) return id;
  }
  return null;
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

/** Advisory manifest warnings (sc#66: duplicate-module collisions) attached to
 *  a sim/synth dispatch reply. Surfaced as warnings ONLY — one toast per
 *  warning, never blocking and never changing the run's own pass/fail
 *  narration (invariant 4: warnings render as warnings). */
function notifyManifestWarnings(
  store: ReturnType<typeof useStore.getState>,
  warnings: string[] | undefined
): void {
  for (const w of warnings ?? []) {
    store.pushToast({ kind: "info", title: "Manifest warning", detail: w });
  }
}

/** "· N manifest warning(s)" suffix for activity summaries (empty when none). */
function warningsSuffix(warnings: string[] | undefined): string {
  const n = warnings?.length ?? 0;
  return n > 0 ? ` · ${n} manifest warning${n === 1 ? "" : "s"}` : "";
}

/** What a runCommand call amounted to — mirrored back to callers (the Command
 *  Surface) so their own chrome (spinner, result pane) can be truthful. The
 *  nothing-ran cases (no session, duplicate while in flight) return `ok:false`
 *  with `ran:false` — never `null`, which callers used to conflate with a
 *  successful async dispatch (dev#51). */
export interface CommandOutcome {
  ok: boolean;
  /** The same one-liner recorded on the local activity event. */
  summary: string;
  runId: string | null;
  /** False when nothing was executed at all (no session / duplicate in-flight)
   *  — no activity event, no toast, nothing to follow in Activity/Runs. */
  ran: boolean;
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

export async function runCommand(
  id: CommandId,
  values?: CommandValues
): Promise<CommandOutcome> {
  const store = useStore.getState();
  const session = store.currentSession;
  const cmd = COMMANDS[id];
  // Nothing-ran guards return a distinguishable outcome instead of null
  // (dev#51): callers that render "Dispatched" on a successful async dispatch
  // must be able to tell these apart from one.
  if (!session) {
    return { ok: false, summary: "No active session", runId: null, ran: false };
  }
  if (inFlight.has(id)) {
    return {
      ok: false,
      summary: `${cmd.label} is already running — wait for it to finish`,
      runId: null,
      ran: false,
    };
  }
  inFlight.add(id);
  const sessionId = session.id;
  const ui = useWorkbenchUiStore.getState();
  const vals = { ...defaultValues(id, { manifest: store.manifest, runs: store.runs }), ...(values ?? {}) };

  const ev = localEvent(cmd.tool, vals);
  store.appendLocalActivity(ev);
  let outcome: CommandOutcome | null = null;
  const done = (patch: Partial<ActivityEvent>) => {
    // Every terminal narration doubles as the caller-visible outcome (dev#51:
    // the Command Surface awaits this instead of fire-and-forgetting).
    outcome = {
      ok: patch.status !== "error",
      summary: patch.resultSummary ?? "",
      runId: patch.runId ?? null,
      ran: true,
    };
    useStore.getState().appendLocalActivity({
      ...ev,
      durationMs: Date.now() - new Date(ev.ts).getTime(),
      ...patch,
    });
  };
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
        const { run, manifestWarnings } = await workbenchApi.simulate(sessionId, {
          mode: String(vals.mode ?? "rtl"),
          // Empty = let the backend fall back to the manifest's default TB.
          ...(simTop ? { simTop } : {}),
        });
        done({
          status: run.status === "passed" ? "ok" : "error",
          runId: run.id,
          resultSummary:
            (run.status === "passed"
              ? `${run.id} passed`
              : `${run.id} failed${run.failure?.timeNs != null ? ` @ ${run.failure.timeNs}ns` : ""}`) +
            warningsSuffix(manifestWarnings),
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
        notifyManifestWarnings(store, manifestWarnings);
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
        const { runId } = dispatch;
        // /synthesize carries advisory manifestWarnings; /runs/{id}/retry does
        // not (a PD retry reuses the source run's netlist — no compile set).
        const manifestWarnings =
          id === "synth" ? (dispatch as { manifestWarnings?: string[] }).manifestWarnings : undefined;
        inFlight.delete(id); // dispatched — a second job may now be queued
        done({ runId, resultSummary: `${runId} dispatched${warningsSuffix(manifestWarnings)}` });
        store.pushToast({
          kind: "info",
          title: id === "synth" ? "Synthesis dispatched" : "P&R retry dispatched",
          detail: `run ${runId}`,
        });
        notifyManifestWarnings(store, manifestWarnings);
        // Dispatch-only: the finally-block refresh() below pulls the run list
        // once so the new queued/running row appears. No polling — completion
        // reaches the runs slice via activity events / user Refresh / focus
        // revalidate, and the store's transition detector handles the rest
        // (unread, toasts, artifact refresh, dir invalidation).
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
  // Every switch arm narrates through done() (the catch does too), so outcome
  // is always set by here; the fallback only satisfies the type system.
  return outcome ?? { ok: false, summary: "", runId: null, ran: false };
}
