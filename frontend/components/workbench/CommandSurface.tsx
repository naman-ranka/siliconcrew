"use client";

import * as React from "react";
import {
  Activity,
  ArrowRight,
  BarChart3,
  ChevronDown,
  ChevronRight,
  CircuitBoard,
  ClipboardList,
  Cpu,
  Crown,
  FileCode2,
  FileText,
  FlaskConical,
  Gauge,
  GitCompare,
  Info,
  ListTree,
  Loader2,
  LogIn,
  MonitorPlay,
  Package,
  PenLine,
  RefreshCw,
  Search,
  Settings2,
  Terminal,
  Waves,
  X,
  type LucideIcon,
} from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  buildSurfaceCommands,
  buildSurfacePayload,
  resolveOptions,
  runSurfaceCommand,
  surfaceDefaults,
  type SurfaceCommand,
  type SurfaceCtx,
  type SurfaceParam,
  type SurfaceParamSource,
  type SurfaceRunResult,
} from "@/lib/commandSurface";
import { manifestSetPlaceholder } from "@/lib/schemaForm";
import { useStore } from "@/lib/store";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { useAuth } from "@/lib/auth";
import { useElapsedSeconds } from "@/lib/useElapsed";
import { stashAuthIntent, takeAuthIntent } from "@/lib/authIntent";
import {
  ComboInput,
  MultiComboInput,
  type ComboSuggestion,
} from "@/components/workbench/ComboInput";
import { cn } from "@/lib/utils";

// The v2 Command Surface — a three-pane command → tool-call explorer. Left: the
// SCHEMA-DRIVEN catalog (the backend's introspected tool registry) with the
// four core flow commands pinned first; center: the param form (manifest
// supplies files/tops — shown, never asked); right: the LIVE payload that
// buildSurfacePayload will send, plus invoke + inline result.

// ---- icons -------------------------------------------------------------------

// The one genuinely PRESENTATIONAL map left: which glyph a tool wears. Nothing
// in the catalog can supply it, so it is hand-kept — and bound to the registry
// by test/toolRegistry.coverage.test.ts, which fails when a catalog tool has no
// icon (it silently fell back to a generic Terminal, which is how
// build_interactive_sim and run_python_analysis went unnoticed) and when a key
// here no longer names a live tool.
//
// Keyed by command id — the core four keep their short ids; schema-driven
// commands use their tool name as id.
export const SURFACE_ICONS: Record<string, LucideIcon> = {
  lint: FileText,
  sim: Waves,
  synth: Cpu,
  pnr: CircuitBoard,
  waveform_tool: Activity,
  build_interactive_sim: MonitorPlay,
  cocotb_tool: FlaskConical,
  sby_tool: CircuitBoard,
  get_synthesis_metrics: Gauge,
  get_synthesis_status: Gauge,
  read_stage_report: ClipboardList,
  compare_pd_runs: GitCompare,
  search_logs_tool: Search,
  schematic_tool: CircuitBoard,
  get_manifest: Settings2,
  update_manifest: Settings2,
  generate_report_tool: BarChart3,
  run_python_analysis: FileCode2,
  write_spec: FileText,
  read_spec: FileText,
  write_file: FileText,
  read_file: FileText,
  list_files_tool: ListTree,
  edit_file: PenLine,
  run_xls_flow: Package,
};

const iconFor = (id: string): LucideIcon => SURFACE_ICONS[id] ?? Terminal;

// ---- source badges (same idiom as CommandModal) -------------------------------

const SOURCE_STYLES: Record<SurfaceParamSource, string> = {
  manifest: "border-info/30 bg-info/10 text-info",
  choice: "border-warning/30 bg-warning/10 text-warning",
  run: "border-success/30 bg-success/10 text-success",
  default: "border-border bg-surface-2 text-muted-foreground",
  text: "border-border bg-surface-2 text-muted-foreground",
};

function SrcTag({ source }: { source: SurfaceParamSource }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1 py-px font-mono text-[9px] leading-3",
        SOURCE_STYLES[source]
      )}
    >
      {source}
    </span>
  );
}

// ---- tiny primitives -----------------------------------------------------------

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border border-border transition-colors",
        checked ? "bg-primary" : "bg-surface-2"
      )}
    >
      <span
        className={cn(
          "block h-3.5 w-3.5 rounded-full bg-background shadow transition-transform",
          checked ? "translate-x-[18px]" : "translate-x-[2px]"
        )}
      />
    </button>
  );
}

function Collapsible({
  title,
  tint,
  open,
  onToggle,
  children,
}: {
  title: React.ReactNode;
  tint?: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        className={cn(
          "flex w-full items-center gap-1 py-1 text-xs text-muted-foreground transition-colors hover:text-foreground",
          tint
        )}
      >
        {open ? (
          <ChevronDown className="h-3 w-3" aria-hidden />
        ) : (
          <ChevronRight className="h-3 w-3" aria-hidden />
        )}
        <span>{title}</span>
      </button>
      {open && <div className="mt-1.5 space-y-3">{children}</div>}
    </div>
  );
}

// ---- XSS-safe JSON syntax tinting (React nodes, no innerHTML) -------------------

const OMIT_SENTINEL = "__omit__";

function jsonNodes(v: unknown, indent: number): React.ReactNode {
  const pad = "  ".repeat(indent);
  if (v === null || v === undefined)
    return <span className="text-muted-foreground">null</span>;
  if (typeof v === "string")
    return <span className="text-status-pass">{JSON.stringify(v)}</span>;
  if (typeof v === "number")
    return <span className="text-primary">{Number.isFinite(v) ? String(v) : "null"}</span>;
  if (typeof v === "boolean")
    return <span className="text-status-warn">{String(v)}</span>;
  if (Array.isArray(v)) {
    if (v.length === 0) return <span>[]</span>;
    return (
      <>
        {"[\n"}
        {v.map((item, i) => (
          <React.Fragment key={i}>
            {pad + "  "}
            {jsonNodes(item, indent + 1)}
            {i < v.length - 1 ? "," : ""}
            {"\n"}
          </React.Fragment>
        ))}
        {pad + "]"}
      </>
    );
  }
  if (typeof v === "object") {
    const entries = Object.entries(v as Record<string, unknown>);
    if (entries.length === 0) return <span>{"{}"}</span>;
    return (
      <>
        {"{\n"}
        {entries.map(([k, val], i) => (
          <React.Fragment key={k}>
            {pad + "  "}
            <span className="text-info">{JSON.stringify(k)}</span>
            {": "}
            {jsonNodes(val, indent + 1)}
            {i < entries.length - 1 ? "," : ""}
            {"\n"}
          </React.Fragment>
        ))}
        {pad + "}"}
      </>
    );
  }
  return <span>{String(v)}</span>;
}

function JsonView({ value, ariaLabel }: { value: unknown; ariaLabel?: string }) {
  return (
    <pre
      aria-label={ariaLabel}
      className="whitespace-pre font-mono text-[11px] leading-relaxed text-foreground"
    >
      {jsonNodes(value, 0)}
    </pre>
  );
}

// ---- param editors (CommandModal idioms + the surface's "multi" chips) ----------

/** Combo rows: the value, plus a display-only subtitle when one is known. */
function withSubtitles(
  values: string[] | undefined,
  subtitles?: Record<string, string>
): ComboSuggestion[] | undefined {
  return values?.map((o) => (subtitles?.[o] ? { value: o, subtitle: subtitles[o] } : o));
}

function ParamEditor({
  param,
  options,
  subtitles,
  morePaths,
  value,
  onChange,
}: {
  param: SurfaceParam;
  options: string[];
  /** value → subtitle map for combo rows (module → file, file → role). */
  subtitles?: Record<string, string>;
  /** The wider workspace path index — the combo's SECOND tier, surfaced only
   *  once the user types (owner refinement 2026-08-14). File fields only. */
  morePaths?: string[];
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const suggestions = withSubtitles(options, subtitles) ?? [];
  const more = withSubtitles(morePaths, subtitles);
  switch (param.editor) {
    case "enum": {
      // Short small sets → segmented buttons; long values or >4 options →
      // dropdown. Empty string (optional run) renders as "(omit)".
      const segmented =
        options.length > 0 && options.length <= 4 && options.every((o) => o.length <= 12);
      if (segmented) {
        return (
          <div className="inline-flex overflow-hidden rounded-md border border-border">
            {options.map((opt) => (
              <button
                key={opt || OMIT_SENTINEL}
                type="button"
                onClick={() => onChange(opt)}
                className={cn(
                  "border-r border-border px-2.5 py-1 font-mono text-[11px] transition-colors last:border-r-0",
                  value === opt
                    ? "bg-primary/15 text-primary"
                    : "bg-transparent text-muted-foreground hover:bg-surface-2 hover:text-foreground"
                )}
              >
                {opt === "" ? "(omit)" : opt}
              </button>
            ))}
          </div>
        );
      }
      return (
        <Select
          value={value === "" || value == null ? OMIT_SENTINEL : String(value)}
          onValueChange={(v) => onChange(v === OMIT_SENTINEL ? "" : v)}
        >
          <SelectTrigger className="h-7 w-52 font-mono text-[11px]">
            <SelectValue placeholder="Select…" />
          </SelectTrigger>
          <SelectContent>
            {options.map((opt) => (
              <SelectItem
                key={opt || OMIT_SENTINEL}
                value={opt === "" ? OMIT_SENTINEL : opt}
                className="font-mono text-[11px]"
              >
                {opt === "" ? "(omit)" : opt}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      );
    }
    case "bool":
      return <Toggle checked={Boolean(value)} onChange={onChange} label={param.label} />;
    case "number":
      return (
        <div className="relative w-36">
          <Input
            type="number"
            value={value === "" || value == null ? "" : String(value)}
            step={param.step}
            min={param.min}
            max={param.max}
            onChange={(e) => {
              const raw = e.target.value;
              onChange(raw === "" ? "" : Number(raw));
            }}
            className={cn("h-7 font-mono text-[11px]", param.unit && "pr-9")}
          />
          {param.unit && (
            <span className="pointer-events-none absolute inset-y-0 right-2.5 flex items-center font-mono text-[10px] text-muted-foreground">
              {param.unit}
            </span>
          )}
        </div>
      );
    case "text":
      return (
        <Input
          type="text"
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
          className="h-7 w-52 font-mono text-[11px]"
        />
      );
    case "combo":
      return (
        <ComboInput
          value={String(value ?? "")}
          onChange={(v) => onChange(v)}
          suggestions={suggestions}
          moreSuggestions={more}
          ariaLabel={param.label}
          placeholder={param.placeholder}
          className="w-52"
        />
      );
    case "json":
      // W7/A24: dict / list[dict] params get a real JSON textarea (validated
      // client-side by jsonParamErrors before anything is sent).
      return (
        <textarea
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
          aria-label={param.label}
          rows={5}
          spellCheck={false}
          placeholder={
            param.jsonKind === "array" ? '[{ "name": "clk", "dir": "input" }]' : '{ "WIDTH": 8 }'
          }
          className={cn(
            "w-64 rounded-md border border-border bg-surface-1 p-2 font-mono text-[11px] leading-relaxed text-foreground",
            "outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-primary/60"
          )}
        />
      );
    case "multi": {
      const arr = Array.isArray(value) ? (value as string[]) : [];
      // ONE selector everywhere (W2): chips + a suggesting combo to add
      // entries — free entry always allowed, suggestions when the workspace
      // supplies them (empty pool = plain type-and-Enter).
      return (
        <MultiComboInput
          values={arr}
          onChange={onChange}
          suggestions={suggestions}
          moreSuggestions={more}
          ariaLabel={`Add ${param.label}`}
          placeholder={param.placeholder}
        />
      );
    }
  }
}

function ParamRow({
  param,
  options,
  subtitles,
  morePaths,
  value,
  error,
  onChange,
}: {
  param: SurfaceParam;
  options: string[];
  subtitles?: Record<string, string>;
  morePaths?: string[];
  value: unknown;
  /** Server-side field error (400 invalid_arguments) — shown until edited. */
  error?: string | null;
  onChange: (v: unknown) => void;
}) {
  const noRuns =
    param.source === "run" && options.filter((o) => o !== "").length === 0;
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="flex w-40 shrink-0 items-center gap-1.5 pt-1">
        <span
          className={cn(
            "truncate font-mono text-xs",
            error ? "text-status-fail" : "text-foreground"
          )}
        >
          {param.label}
        </span>
        <SrcTag source={param.source} />
        {param.valueKind && (
          <span className="inline-flex items-center rounded border border-border bg-surface-2 px-1 py-px font-mono text-[9px] leading-3 text-muted-foreground">
            {param.valueKind}
          </span>
        )}
      </div>
      <div className="flex min-w-0 flex-1 flex-col items-end gap-1">
        {noRuns ? (
          <span className="text-[11px] italic text-muted-foreground">No synth runs yet</span>
        ) : (
          <ParamEditor
            param={param}
            options={options}
            subtitles={subtitles}
            morePaths={morePaths}
            value={value}
            onChange={onChange}
          />
        )}
        {error && (
          <span className="text-[10px] text-status-fail">{error}</span>
        )}
        {param.hint && !noRuns && (
          <span className="text-[10px] italic text-muted-foreground">{param.hint}</span>
        )}
      </div>
    </div>
  );
}

// ---- file-override box (L1) ---------------------------------------------------------

/**
 * The editable successor of the "Supplied by manifest — not asked of the
 * user" box for a `type: "files"` registry param: collapsed, it shows the
 * manifest set as chips; "Override…" swaps in the multi-combo (chips +
 * suggesting input). An empty override = the backend's manifest resolution,
 * exactly as before — so "Use manifest set" simply clears the list.
 */
function OverrideBox({
  param,
  options,
  subtitles,
  morePaths,
  value,
  error,
  onChange,
}: {
  param: SurfaceParam;
  /** The manifest set — doubles as chips (collapsed) and suggestions (editing). */
  options: string[];
  subtitles?: Record<string, string>;
  /** Second suggestion tier for the editor (typed queries only). */
  morePaths?: string[];
  value: unknown;
  error?: string | null;
  onChange: (v: string[]) => void;
}) {
  const arr = Array.isArray(value) ? (value as string[]) : [];
  const [editing, setEditing] = React.useState(false);
  const active = editing || arr.length > 0;
  return (
    <div
      data-testid={`command-surface-override-${param.key}`}
      className="mt-4 rounded-lg border border-info/25 bg-info/5 p-3"
    >
      <div className="mb-2 flex items-center gap-1.5">
        <Info className="h-3.5 w-3.5 text-info" aria-hidden />
        <span className="text-[11px] font-semibold text-info">
          {active ? "Overriding the manifest set" : "Supplied by manifest"}
          {" · "}
          <code className="font-mono">{param.key}</code>
        </span>
        <button
          type="button"
          onClick={() => {
            if (active) {
              onChange([]); // empty = manifest-driven again
              setEditing(false);
            } else {
              setEditing(true);
            }
          }}
          className="ml-auto shrink-0 text-[11px] text-info underline-offset-2 hover:underline"
        >
          {active ? "Use manifest set" : "Override…"}
        </button>
      </div>
      {active ? (
        <div className="flex flex-col gap-1">
          <MultiComboInput
            values={arr}
            onChange={onChange}
            suggestions={withSubtitles(options, subtitles) ?? []}
            moreSuggestions={withSubtitles(morePaths, subtitles)}
            ariaLabel={`Override ${param.key}`}
            // Empty override = the manifest set, said out loud in the input.
            placeholder={options.length > 0 ? manifestSetPlaceholder(options) : undefined}
            className="max-w-none items-start"
          />
          {param.hint && (
            <span className="text-[10px] italic text-muted-foreground">{param.hint}</span>
          )}
          {error && <span className="text-[10px] text-status-fail">{error}</span>}
        </div>
      ) : (
        <div className="flex flex-wrap gap-1">
          {options.length > 0 ? (
            options.map((o) => (
              <span
                key={o}
                className="rounded border border-border bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] text-foreground"
              >
                {o}
              </span>
            ))
          ) : (
            <span className="font-mono text-[11px] text-muted-foreground">—</span>
          )}
        </div>
      )}
    </div>
  );
}

// ---- right-pane endpoint label ---------------------------------------------------

const CORE_PATHS: Record<string, string> = {
  lint: "POST /lint",
  sim: "POST /simulate",
  synth: "POST /synthesize",
  pnr: "POST /runs/{id}/retry",
};

function endpointLabel(cmd: SurfaceCommand): string {
  if (cmd.tool === "update_manifest") return "PUT /manifest";
  if (cmd.core) return CORE_PATHS[cmd.id] ?? `POST /invoke · ${cmd.tool}`;
  return `POST /invoke · ${cmd.tool}`;
}

// ---- the surface -----------------------------------------------------------------

/** The rail's opening selection (also where a session switch returns to). */
const DEFAULT_COMMAND_ID = "synth";

export function CommandSurface() {
  const open = useWorkbenchUiStore((s) => s.commandSurfaceOpen);
  const setOpen = useWorkbenchUiStore((s) => s.setCommandSurfaceOpen);
  const currentSession = useStore((s) => s.currentSession);
  const manifest = useStore((s) => s.manifest);
  const runs = useStore((s) => s.runs);
  const pathIndex = useStore((s) => s.pathIndex);
  const loadPathIndex = useStore((s) => s.loadPathIndex);
  const toolCatalog = useStore((s) => s.toolCatalog);
  const loadToolCatalog = useStore((s) => s.loadToolCatalog);

  const [selectedId, setSelectedId] = React.useState(DEFAULT_COMMAND_ID);
  const [values, setValues] = React.useState<Record<string, Record<string, unknown>>>({});
  const [advOpen, setAdvOpen] = React.useState(false);
  const [resultOpen, setResultOpen] = React.useState(true);
  // In-flight invokes keyed by the session they were made FOR (finding 2 of
  // the PR review): a slow call in session A must not disable session B's
  // Invoke button or show B a "Running — Ns" clock for a command B never
  // invoked, and A's late `finally` must not clear a run B has since started.
  // `running` below is the derived read for the CURRENT session only.
  const [inFlight, setInFlight] = React.useState<Record<string, true>>({});
  const [results, setResults] = React.useState<Record<string, SurfaceRunResult>>({});
  // Per-command last successful async dispatch (W5/A20): the run id feeds the
  // dispatch note + "View in Runs" and the F1 guard. Absent = nothing
  // dispatched. `noteVisible` is the note's own lifetime (this visit); the
  // record outlives it — see the close effect below (P2-4).
  const [dispatched, setDispatched] = React.useState<
    Record<string, { runId: string | null; noteVisible: boolean } | undefined>
  >({});
  // F1: the explicit "yes, dispatch a SECOND job" acknowledgement. Never
  // sticky — cleared on close, on a session switch, and on every dispatch.
  const [rearmed, setRearmed] = React.useState<Record<string, boolean>>({});
  // Server-side field errors from the last invoke, keyed cmd.id → field →
  // message. A field's message clears as soon as the user edits it.
  const [fieldErrs, setFieldErrs] = React.useState<Record<string, Record<string, string>>>({});
  // W6: rail filter query (substring over label + tool name + category).
  const [railQ, setRailQ] = React.useState("");
  const rightBodyRef = React.useRef<HTMLDivElement>(null);
  const centerRef = React.useRef<HTMLDivElement>(null);
  const filterRef = React.useRef<HTMLInputElement>(null);
  const { status: authStatus, signIn } = useAuth();
  const running = Boolean(currentSession && inFlight[currentSession.id]);
  // W5: client-side clock for the sync "Running — Ns" indicator (a clock,
  // never a poller — invariant 6). Follows the per-session read, so a switch
  // freezes it and the next invoke in the new session restarts it from 0.
  const elapsed = useElapsedSeconds(running);

  // F1 (adversarial review): the Surface stays MOUNTED when it closes, so its
  // state outlives the dialog. A "Dispatched — synth_0042" note from an
  // earlier visit is stale on reopen (and the run it names may be long done),
  // so the note and any re-arm acknowledgement die with the dialog. The
  // dispatch RECORD does not (P2-4): it is the only honest evidence that a
  // paid job went out until the runs slice shows that run finished — and the
  // slice is filtered by runKindFilter, so it may never show it. It dies on
  // a session switch (F3) or when the slice proves the run terminal.
  React.useEffect(() => {
    if (open) return;
    setDispatched((prev) => {
      if (!Object.values(prev).some((d) => d?.noteVisible)) return prev;
      return Object.fromEntries(
        Object.entries(prev).map(([k, d]) => [k, d && { ...d, noteVisible: false }])
      );
    });
    setRearmed((prev) => (Object.keys(prev).length === 0 ? prev : {}));
  }, [open]);

  // F3 (adversarial review): reset per-session form state on a session switch
  // — the documented sharp edge (run ids collide across sessions, and a
  // half-filled form for another workspace is a wrong-design hazard). Defined
  // BEFORE the auth-intent replay host so a restored intent always wins.
  const sessionIdRef = React.useRef<string | null>(currentSession?.id ?? null);
  React.useEffect(() => {
    const sid = currentSession?.id ?? null;
    if (sessionIdRef.current === sid) return;
    sessionIdRef.current = sid;
    setValues({});
    setResults({});
    setDispatched({});
    setRearmed({});
    setFieldErrs({});
    setSelectedId(DEFAULT_COMMAND_ID);
  }, [currentSession?.id]);

  // Esc closes (window-level while open; no global shortcut registration).
  React.useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      // House Esc discipline (A23/FA11): consumers (combo dropdowns, the rail
      // filter clearing its text) preventDefault — check FIRST so the
      // Surface never closes over an inner consumer's Esc.
      if (e.defaultPrevented) return;
      e.preventDefault();
      setOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, setOpen]);

  // W6: opening focuses the rail filter (type-to-filter, mirroring ⌘K).
  React.useEffect(() => {
    if (open) filterRef.current?.focus();
  }, [open]);

  // W4/A18: the Surface's auth-intent replay host. After the sign-in round
  // trip (WorkOS full-page redirect via the Launcher re-stash, or Google/GIS
  // in place), restore the exact command + form values the signed-out user
  // had, and reopen the Surface. Kind-scoped take: other hosts' intents are
  // left alone; a mismatched session drops the intent (cleared, never
  // replayed against the wrong workspace).
  React.useEffect(() => {
    if (authStatus !== "signed_in" || !currentSession) return;
    const intent = takeAuthIntent("surfaceCommand");
    if (!intent || intent.kind !== "surfaceCommand") return;
    if (intent.sessionId !== currentSession.id) return;
    setSelectedId(intent.commandId);
    setValues((prev) => ({ ...prev, [intent.commandId]: intent.values }));
    // P3-5: on the in-place (Google/GIS) path the Surface never unmounted, so
    // the `signinRequired` result that raised the CTA is still in the pane —
    // "Sign in to run this" after the user IS signed in. The result is about
    // a state that no longer holds; drop it.
    setResults((prev) => {
      if (!(intent.commandId in prev)) return prev;
      const next = { ...prev };
      delete next[intent.commandId];
      return next;
    });
    setOpen(true);
  }, [authStatus, currentSession, setOpen]);

  // The introspected catalog loads once per app lifetime (store-guarded);
  // the recursive path index loads per session on open (SWR-cached — a cheap
  // no-op when already populated; invalidateDirs revalidates it).
  React.useEffect(() => {
    if (!open) return;
    void loadToolCatalog();
    void loadPathIndex();
  }, [open, currentSession?.id, loadToolCatalog, loadPathIndex]);

  const ctx: SurfaceCtx = React.useMemo(
    () => ({
      manifest,
      runs,
      wsPaths: pathIndex.paths,
      wsPathsTruncated: pathIndex.truncated,
    }),
    [manifest, runs, pathIndex]
  );

  // Flow (core four) + the schema-driven groups from the backend catalog.
  const surfaceGroups = React.useMemo(
    () => buildSurfaceCommands(toolCatalog.tools, ctx).groups,
    [toolCatalog.tools, ctx]
  );
  const allCommands = React.useMemo(
    () => surfaceGroups.flatMap((g) => g.commands),
    [surfaceGroups]
  );

  // W6: the rail filtered by the query — a group disappears when none of its
  // commands match; selection is NOT forced to stay in the filtered set (the
  // rail is selection-stateful — the open form keeps showing). Everything
  // matched against is catalog-derived (label, tool name, category label).
  const visibleGroups = React.useMemo(() => {
    const needle = railQ.trim().toLowerCase();
    if (!needle) return surfaceGroups;
    return surfaceGroups
      .map((g) => ({
        label: g.label,
        commands: g.commands.filter((c) =>
          [c.label, c.tool, g.label].some((t) => t.toLowerCase().includes(needle))
        ),
      }))
      .filter((g) => g.commands.length > 0);
  }, [surfaceGroups, railQ]);

  if (!open || !currentSession) return null;

  const catalogLoading =
    toolCatalog.status === "loading" || toolCatalog.status === "empty";
  const catalogError = toolCatalog.status === "error" ? toolCatalog.error : null;

  const cmd = allCommands.find((c) => c.id === selectedId) ?? allCommands[0];
  const Icon = iconFor(cmd.id);

  const facts = cmd.facts?.(ctx) ?? [];
  const userVals = values[cmd.id] ?? {};
  const merged = { ...surfaceDefaults(cmd, ctx), ...userVals };
  const payload = buildSurfacePayload(cmd, userVals, ctx);

  const selectCommand = (id: string) => {
    setSelectedId(id);
    // Reset per-command chrome on switch: advanced collapsed, result expanded,
    // both scroll containers back to top.
    setAdvOpen(false);
    setResultOpen(true);
    if (rightBodyRef.current) rightBodyRef.current.scrollTop = 0;
    if (centerRef.current) centerRef.current.scrollTop = 0;
  };

  // W6: filter-input keyboard nav — ↑/↓ move the SELECTION through the
  // visible (filtered) list (wrapping), Enter snaps to the first match when
  // the current selection was filtered away. Esc with text clears it
  // (consumed — the Surface's window listener sees defaultPrevented and stays
  // open); Esc with empty text is left alone, so the Surface closes.
  const flatVisible = visibleGroups.flatMap((g) => g.commands);
  const onFilterKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      if (railQ) {
        e.preventDefault();
        e.stopPropagation();
        setRailQ("");
      }
      return;
    }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (flatVisible.length === 0) return;
      const idx = flatVisible.findIndex((c) => c.id === selectedId);
      const next =
        idx < 0
          ? e.key === "ArrowDown"
            ? 0
            : flatVisible.length - 1
          : (idx + (e.key === "ArrowDown" ? 1 : -1) + flatVisible.length) % flatVisible.length;
      selectCommand(flatVisible[next].id);
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      if (flatVisible.length === 0) return;
      if (!flatVisible.some((c) => c.id === selectedId)) selectCommand(flatVisible[0].id);
    }
  };

  // W4/L2: the sign-in CTA — stash the exact command + form state, then start
  // sign-in. The replay host above restores both when the round trip lands.
  const signInToRun = () => {
    stashAuthIntent({
      kind: "surfaceCommand",
      sessionId: currentSession.id,
      commandId: cmd.id,
      values: userVals,
    });
    signIn();
  };

  const setValue = (key: string, v: unknown) => {
    setValues((prev) => ({
      ...prev,
      [cmd.id]: { ...(prev[cmd.id] ?? {}), [key]: v },
    }));
    // Editing a field clears its server-side error marker.
    setFieldErrs((prev) => {
      const forCmd = prev[cmd.id];
      if (!forCmd || !(key in forCmd)) return prev;
      const { [key]: _drop, ...rest } = forCmd;
      return { ...prev, [cmd.id]: rest };
    });
  };

  // Owner refinement (2026-08-14): every FILE field's combo gets a second
  // tier — the whole workspace path index — revealed only once the user
  // types. The suggested tier still leads; nothing the workspace holds is
  // unreachable. Module/run/enum fields are untouched (a run id is a closed
  // set; a module is not a path).
  const morePathsFor = (p: SurfaceParam): string[] | undefined =>
    p.valueKind === "file" && ctx.wsPaths.length > 0 ? ctx.wsPaths : undefined;

  const visible = cmd.params.filter((p) => !p.when || p.when(merged));
  // L1: override params render as the manifest box, never as plain rows.
  const overrides = visible.filter((p) => p.override);
  const basic = visible.filter((p) => !p.adv && !p.override);
  const advanced = visible.filter((p) => p.adv && !p.override);

  const missingRun = visible.some(
    (p) =>
      p.source === "run" &&
      !p.optional &&
      resolveOptions(p, ctx).filter((o) => o !== "").length === 0
  );

  const result = results[cmd.id];
  const wasDispatched = dispatched[cmd.id];

  // F1: a second click on Dispatch starts a second (paid, on hosted) job. An
  // async command that produces a run row (registry `producesRun`, FA9) is
  // disarmed — one explicit "Dispatch again?" re-arms it — whenever either
  // honest read says a job of this kind may still be in flight:
  //   * this Surface dispatched one (the record survives close → reopen;
  //     only the note is per visit) and the runs slice has not yet shown
  //     that run reaching a terminal state, or
  //   * the runs slice carries a live run of the kind this command produces.
  // Both are reads of already-loaded state; the Surface still never polls.
  // The runs slice is scoped by runKindFilter, so "as far as this view knows"
  // in the copy below is load-bearing, not decoration.
  const guarded = Boolean(cmd.async && cmd.producesRun);
  const dispatchedRun = wasDispatched?.runId
    ? runs.find((r) => r.id === wasDispatched.runId)
    : undefined;
  const liveDispatch =
    Boolean(wasDispatched) && (!dispatchedRun || dispatchedRun.status === "running");
  const liveRun =
    guarded && runs.some((r) => r.kind === cmd.producesRun && r.status === "running");
  const needsRearm = guarded && (liveDispatch || liveRun) && !rearmed[cmd.id];

  const invoke = async () => {
    if (running || missingRun || needsRearm) return;
    // Stale-response guard (the store's idiom for every cross-session async):
    // the session this call was made FOR. A switch mid-flight resets the
    // Surface (F3), and the late result must not land in the next workspace's
    // pane — a wrong-session verdict, dispatch note or re-arm lock.
    const sid = currentSession.id;
    setInFlight((prev) => ({ ...prev, [sid]: true }));
    setDispatched((prev) => ({ ...prev, [cmd.id]: undefined }));
    // Each dispatch consumes the acknowledgement — the NEXT one asks again.
    setRearmed((prev) => (prev[cmd.id] ? { ...prev, [cmd.id]: false } : prev));
    try {
      // Pass only the user-touched values — runSurfaceCommand merges defaults.
      const res = await runSurfaceCommand(cmd, userVals);
      if (useStore.getState().currentSession?.id !== sid) return; // switched away mid-flight
      if (res.dispatched) {
        // A successful async core dispatch (W5/A20 — explicit flag + run id,
        // replacing the old null contract): the note below is truthful by
        // construction. Drop any stale result from a previous failed attempt
        // so the pane doesn't contradict the dispatch note.
        setDispatched((prev) => ({
          ...prev,
          [cmd.id]: { runId: res.runId ?? null, noteVisible: true },
        }));
        setResults((prev) => {
          if (!(cmd.id in prev)) return prev;
          const next = { ...prev };
          delete next[cmd.id];
          return next;
        });
      } else {
        setResults((prev) => ({ ...prev, [cmd.id]: res }));
        setFieldErrs((prev) => ({
          ...prev,
          [cmd.id]: Object.fromEntries(
            (res.fieldErrors ?? []).map((f) => [f.field, f.message])
          ),
        }));
        setResultOpen(true);
      }
    } finally {
      // Clear only THIS session's slot — never a run another session started
      // while this one was in flight.
      setInFlight((prev) => {
        if (!(sid in prev)) return prev;
        const next = { ...prev };
        delete next[sid];
        return next;
      });
    }
  };

  // W5/A22: an explicit user gesture — open the dock's Runs tab (expanding a
  // collapsed dock) and close the Surface. Never automatic (invariant 4).
  const viewInRuns = () => {
    const ui = useWorkbenchUiStore.getState();
    ui.setDockTab(currentSession.id, "runs");
    ui.setDockCollapsed(currentSession.id, false);
    setOpen(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop — click closes. */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={() => setOpen(false)}
        aria-hidden
      />

      <div
        data-testid="command-surface"
        role="dialog"
        aria-modal="true"
        aria-label="Command surface"
        className="relative flex h-[min(760px,90vh)] w-[min(1200px,94vw)] flex-col overflow-hidden rounded-lg border border-border bg-background shadow-e3"
      >
        {/* ---- Header ---- */}
        <div className="flex h-10 shrink-0 items-center gap-2 border-b border-border bg-surface-1 px-3">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded bg-primary/15">
            <Terminal className="h-3.5 w-3.5 text-primary" aria-hidden />
          </span>
          <span className="text-[13px] font-semibold text-foreground">Command surface</span>
          <span className="truncate text-[10px] text-muted-foreground">
            command → tool call · manifest-driven files, choice-driven params
          </span>
          <div className="ml-auto flex shrink-0 items-center gap-3">
            {manifest && (
              <div className="hidden items-center gap-2 font-mono text-[10px] text-muted-foreground md:flex">
                <span className="inline-flex items-center gap-1">
                  <Crown className="h-3 w-3" aria-hidden />
                  {manifest.synthTop || "—"}
                </span>
                <span aria-hidden>·</span>
                <span className="inline-flex items-center gap-1">
                  <FlaskConical className="h-3 w-3" aria-hidden />
                  {manifest.simTop || "—"}
                </span>
                <span aria-hidden>·</span>
                <span>clk {manifest.clockPeriodNs}ns</span>
                <span aria-hidden>·</span>
                <span>{manifest.platform}</span>
              </div>
            )}
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              aria-label="Close command surface"
              onClick={() => setOpen(false)}
            >
              <X className="h-3.5 w-3.5" aria-hidden />
            </Button>
          </div>
        </div>

        {/* ---- Body: left rail · center form · right payload ---- */}
        <div className="flex min-h-0 flex-1">
          {/* Left rail — filter + grouped command list (Flow pinned; rest schema-driven) */}
          <div className="flex w-[210px] shrink-0 flex-col border-r border-border bg-surface-0">
            <div className="shrink-0 border-b border-border p-2">
              <div className="relative">
                <Search
                  className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground"
                  aria-hidden
                />
                <Input
                  ref={filterRef}
                  type="text"
                  value={railQ}
                  onChange={(e) => setRailQ(e.target.value)}
                  onKeyDown={onFilterKeyDown}
                  placeholder="Filter commands…"
                  aria-label="Filter commands"
                  data-testid="command-surface-filter"
                  className="h-7 pl-6 text-xs"
                />
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto py-1.5">
            {visibleGroups.map((group) => {
              if (group.commands.length === 0) return null;
              return (
                <div key={group.label}>
                  <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                    {group.label}
                  </div>
                  {group.commands.map((c) => {
                    const RowIcon = iconFor(c.id);
                    const selected = c.id === selectedId;
                    return (
                      <button
                        key={c.id}
                        type="button"
                        onClick={() => selectCommand(c.id)}
                        aria-current={selected ? "true" : undefined}
                        className={cn(
                          "relative flex h-8 w-full items-center gap-2 pl-3 pr-2 text-left transition-colors",
                          selected
                            ? "bg-surface-2"
                            : "hover:bg-surface-1"
                        )}
                      >
                        {selected && (
                          <span
                            className="absolute inset-y-0 left-0 w-0.5 bg-primary"
                            aria-hidden
                          />
                        )}
                        <RowIcon
                          className={cn(
                            "h-3.5 w-3.5 shrink-0",
                            selected ? "text-primary" : "text-muted-foreground"
                          )}
                          aria-hidden
                        />
                        <span className="min-w-0 flex-1 truncate text-xs text-foreground">
                          {c.label}
                        </span>
                        {c.async && (
                          <span className="shrink-0 rounded border border-status-running/30 px-1 py-px font-mono text-[8px] uppercase text-status-running">
                            async
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              );
            })}
            {railQ.trim() !== "" && flatVisible.length === 0 && (
              <p className="px-3 py-2 text-[11px] italic text-muted-foreground">
                No matching commands.
              </p>
            )}
            {/* Introspected-catalog states below the always-available Flow group. */}
            {catalogLoading && (
              <div data-testid="command-surface-catalog-loading" className="space-y-2 px-3 py-2">
                {Array.from({ length: 6 }).map((_, i) => (
                  <div
                    key={i}
                    className="h-5 animate-pulse rounded bg-surface-2"
                    aria-hidden
                  />
                ))}
              </div>
            )}
            {catalogError && (
              <div className="mx-3 my-2 rounded border border-status-fail/30 bg-status-fail/5 p-2">
                <p className="text-[11px] leading-snug text-status-fail">{catalogError}</p>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="mt-1.5 h-6 gap-1 px-1.5 text-[11px]"
                  onClick={() => void loadToolCatalog()}
                >
                  <RefreshCw className="h-3 w-3" aria-hidden />
                  Retry
                </Button>
              </div>
            )}
            </div>
          </div>

          {/* Center — param form */}
          <div ref={centerRef} className="min-w-0 flex-1 overflow-y-auto">
            <div className="mx-auto max-w-2xl p-5">
              <div className="flex items-center gap-2.5">
                <Icon className="h-5 w-5 text-primary" aria-hidden />
                <h2 className="text-lg font-semibold text-foreground">{cmd.label}</h2>
                <code className="rounded border border-border bg-surface-2 px-1.5 font-mono text-[11px] text-muted-foreground">
                  {cmd.tool}
                </code>
                {cmd.async && (
                  <span className="inline-flex items-center gap-1 rounded border border-status-running/30 bg-status-running/10 px-1.5 py-px font-mono text-[10px] uppercase text-status-running">
                    <Cpu className="h-3 w-3" aria-hidden />
                    async
                  </span>
                )}
              </div>
              <p className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground">
                {cmd.desc}
              </p>

              {facts.length > 0 && (
                <div className="mt-4 rounded-lg border border-info/25 bg-info/5 p-3">
                  <div className="mb-2 flex items-center gap-1.5">
                    <Info className="h-3.5 w-3.5 text-info" aria-hidden />
                    <span className="text-[11px] font-semibold text-info">
                      Supplied by manifest — not asked of the user
                    </span>
                  </div>
                  <div className="space-y-1">
                    {facts.map((f) => (
                      <div key={f.label} className="flex gap-2 font-mono text-[11px]">
                        <span className="w-28 shrink-0 text-muted-foreground">{f.label}</span>
                        <span className="min-w-0 flex-1 break-words text-foreground">
                          {f.value}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {overrides.map((p) => (
                <OverrideBox
                  // F4: keyed by COMMAND + param. Lint and Simulate both call
                  // their override param `files`, so a bare `p.key` let React
                  // reuse one instance across the switch and carry its
                  // `editing` state (and focus) into the other command's box.
                  key={`${cmd.id}:${p.key}`}
                  param={p}
                  options={resolveOptions(p, ctx)}
                  subtitles={p.subtitles?.(ctx)}
                  morePaths={morePathsFor(p)}
                  value={merged[p.key]}
                  error={fieldErrs[cmd.id]?.[p.key]}
                  onChange={(v) => setValue(p.key, v)}
                />
              ))}

              {basic.length === 0 &&
                advanced.length === 0 &&
                overrides.length === 0 &&
                facts.length === 0 && (
                  <p className="mt-4 text-xs italic text-muted-foreground">
                    No parameters — one-click command.
                  </p>
                )}

              {basic.length > 0 && (
                <div className="mt-4 space-y-3">
                  {basic.map((p) => (
                    <ParamRow
                      key={p.key}
                      param={p}
                      options={resolveOptions(p, ctx)}
                      subtitles={p.subtitles?.(ctx)}
                      morePaths={morePathsFor(p)}
                      value={merged[p.key]}
                      error={fieldErrs[cmd.id]?.[p.key]}
                      onChange={(v) => setValue(p.key, v)}
                    />
                  ))}
                </div>
              )}

              {advanced.length > 0 && (
                <div className="mt-4">
                  <Collapsible
                    title={`Advanced (${advanced.length})`}
                    open={advOpen}
                    onToggle={() => setAdvOpen((o) => !o)}
                  >
                    {advanced.map((p) => (
                      <ParamRow
                        key={p.key}
                        param={p}
                        options={resolveOptions(p, ctx)}
                        subtitles={p.subtitles?.(ctx)}
                        morePaths={morePathsFor(p)}
                        value={merged[p.key]}
                        error={fieldErrs[cmd.id]?.[p.key]}
                        onChange={(v) => setValue(p.key, v)}
                      />
                    ))}
                  </Collapsible>
                </div>
              )}
            </div>
          </div>

          {/* Right pane — live payload + invoke + result */}
          <div className="flex w-[380px] shrink-0 flex-col border-l border-border bg-surface-0 min-h-0">
            <div className="flex h-9 shrink-0 items-center justify-between border-b border-border px-3">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Tool call
              </span>
              <span className="truncate font-mono text-[10px] text-muted-foreground">
                {endpointLabel(cmd)}
              </span>
            </div>

            <div ref={rightBodyRef} className="flex-1 overflow-auto p-3">
              <JsonView value={payload} ariaLabel="tool call payload" />

              {running && !cmd.async && (
                <p
                  data-testid="command-surface-elapsed"
                  className="mt-3 border-t border-border pt-2 font-mono text-[11px] text-muted-foreground"
                >
                  Running — {elapsed}s
                </p>
              )}

              {result && (
                <div className="mt-3 border-t border-border pt-2">
                  <Collapsible
                    title="Result"
                    tint={result.ok ? "text-status-pass" : "text-status-fail"}
                    open={resultOpen}
                    onToggle={() => setResultOpen((o) => !o)}
                  >
                    {result.signinRequired ? (
                      // W4/L2: the hosted-anonymous rejection renders as a
                      // sign-in CTA, never a raw error string. The form state
                      // survives the round trip (surfaceCommand auth intent).
                      <div data-testid="command-surface-signin-cta" className="space-y-2">
                        <p className="text-[11px] leading-relaxed text-muted-foreground">
                          This command needs a signed-in account. Your filled-in
                          form comes back after signing in.
                        </p>
                        <Button
                          type="button"
                          size="sm"
                          className="h-7 gap-1.5 text-[11px]"
                          onClick={signInToRun}
                        >
                          <LogIn className="h-3 w-3" aria-hidden />
                          Sign in to run this
                        </Button>
                      </div>
                    ) : typeof result.result === "string" ? (
                      <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-foreground">
                        {result.result}
                      </pre>
                    ) : (
                      <JsonView value={result.result} />
                    )}
                  </Collapsible>
                </div>
              )}
            </div>

            <div className="shrink-0 space-y-2.5 border-t border-border p-3">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[10px] text-muted-foreground">sources</span>
                {(["manifest", "choice", "run", "default"] as const).map((s) => (
                  <SrcTag key={s} source={s} />
                ))}
              </div>
              {ctx.wsPathsTruncated && (
                <p className="text-[10px] text-muted-foreground">
                  Workspace file index truncated — suggestions may be incomplete;
                  any path can still be typed.
                </p>
              )}
              {pathIndex.status === "error" && (
                // P3-4: a failed index fetch keeps the old paths (SWR) or
                // leaves none on a first open — either way the second tier
                // is not what the workspace holds, so say so (invariant 4).
                <p data-testid="command-surface-pathindex-error" className="text-[10px] text-muted-foreground">
                  Workspace file index could not be fetched
                  {pathIndex.error ? ` (${pathIndex.error})` : ""} — suggestions may be
                  stale or incomplete; any path can still be typed.
                </p>
              )}
              <Button
                type="button"
                data-testid="command-surface-invoke"
                className="h-9 w-full gap-1.5 text-xs"
                disabled={running || missingRun || needsRearm}
                onClick={() => void invoke()}
              >
                {running ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                ) : cmd.async && cmd.core ? (
                  <Cpu className="h-3.5 w-3.5" aria-hidden />
                ) : (
                  <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                )}
                {cmd.async && cmd.core ? "Dispatch job" : "Invoke"}
              </Button>
              {needsRearm && (
                <div data-testid="command-surface-rearm" className="space-y-1.5">
                  <p className="text-[10px] leading-relaxed text-muted-foreground">
                    {liveDispatch && wasDispatched?.runId
                      ? `${wasDispatched.runId} has not finished as far as this view knows.`
                      : "A run of this kind is still running as far as this view knows."}{" "}
                    Dispatching again starts a second job.
                  </p>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="h-6 w-full text-[11px]"
                    onClick={() => setRearmed((prev) => ({ ...prev, [cmd.id]: true }))}
                  >
                    Dispatch again?
                  </Button>
                </div>
              )}
              {wasDispatched?.noteVisible && (
                <div data-testid="command-surface-dispatch-note" className="space-y-1.5">
                  <p className="font-mono text-[10px] text-muted-foreground">
                    Dispatched{wasDispatched.runId ? ` — ${wasDispatched.runId}` : ""} · follow
                    it in Activity/Runs
                  </p>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="h-6 w-full gap-1 text-[11px]"
                    onClick={viewInRuns}
                  >
                    View in Runs
                  </Button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default CommandSurface;
