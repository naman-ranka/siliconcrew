"use client";

import * as React from "react";
import {
  Activity,
  ArrowRight,
  BarChart3,
  Boxes,
  ChevronDown,
  ChevronRight,
  CircuitBoard,
  ClipboardList,
  Cpu,
  Crown,
  FileText,
  FlaskConical,
  Gauge,
  GitCompare,
  Info,
  LayoutGrid,
  ListTree,
  Loader2,
  Package,
  PenLine,
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
  SURFACE_COMMANDS,
  SURFACE_GROUPS,
  buildSurfacePayload,
  resolveOptions,
  runSurfaceCommand,
  surfaceCommand,
  surfaceDefaults,
  type SurfaceCommand,
  type SurfaceCtx,
  type SurfaceParam,
  type SurfaceParamSource,
  type SurfaceRunResult,
} from "@/lib/commandSurface";
import { useStore } from "@/lib/store";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { cn } from "@/lib/utils";

// The v2 Command Surface — a three-pane command → tool-call explorer. Left: the
// full curated catalog grouped Build/Verify/Analyze/Author/HLS; center: the
// param form (manifest supplies files/tops — shown, never asked); right: the
// LIVE payload that buildSurfacePayload will send, plus invoke + inline result.

// ---- icons -------------------------------------------------------------------

const SURFACE_ICONS: Record<string, LucideIcon> = {
  lint: FileText,
  sim: Waves,
  synth: Cpu,
  pnr: CircuitBoard,
  wave: Activity,
  cocotb: FlaskConical,
  sby: CircuitBoard,
  metrics: Gauge,
  stage_status: ListTree,
  stage_report: ClipboardList,
  drc: Boxes,
  cts: Activity,
  congestion: LayoutGrid,
  compare: GitCompare,
  search: Search,
  schematic: CircuitBoard,
  manifest: Settings2,
  report: BarChart3,
  save_metrics: PenLine,
  xls: Package,
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

function ParamEditor({
  param,
  options,
  value,
  onChange,
}: {
  param: SurfaceParam;
  options: string[];
  value: unknown;
  onChange: (v: unknown) => void;
}) {
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
    case "multi": {
      const arr = Array.isArray(value) ? (value as string[]) : [];
      return (
        <div className="flex max-w-[300px] flex-wrap justify-end gap-1">
          {options.map((opt) => {
            const on = arr.includes(opt);
            return (
              <button
                key={opt}
                type="button"
                aria-pressed={on}
                onClick={() =>
                  onChange(on ? arr.filter((o) => o !== opt) : [...arr, opt])
                }
                className={cn(
                  "rounded border px-1.5 py-0.5 font-mono text-[10px] transition-colors",
                  on
                    ? "border-primary/40 bg-primary/15 text-primary"
                    : "border-border bg-transparent text-muted-foreground hover:bg-surface-2 hover:text-foreground"
                )}
              >
                {opt}
              </button>
            );
          })}
        </div>
      );
    }
  }
}

function ParamRow({
  param,
  options,
  value,
  onChange,
}: {
  param: SurfaceParam;
  options: string[];
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const noRuns =
    param.source === "run" && options.filter((o) => o !== "").length === 0;
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="flex w-40 shrink-0 items-center gap-1.5 pt-1">
        <span className="truncate font-mono text-xs text-foreground">{param.label}</span>
        <SrcTag source={param.source} />
      </div>
      <div className="flex min-w-0 flex-1 flex-col items-end gap-1">
        {noRuns ? (
          <span className="text-[11px] italic text-muted-foreground">No synth runs yet</span>
        ) : (
          <ParamEditor param={param} options={options} value={value} onChange={onChange} />
        )}
        {param.hint && !noRuns && (
          <span className="text-[10px] italic text-muted-foreground">{param.hint}</span>
        )}
      </div>
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

export function CommandSurface() {
  const open = useWorkbenchUiStore((s) => s.commandSurfaceOpen);
  const setOpen = useWorkbenchUiStore((s) => s.setCommandSurfaceOpen);
  const currentSession = useStore((s) => s.currentSession);
  const manifest = useStore((s) => s.manifest);
  const runs = useStore((s) => s.runs);

  const [selectedId, setSelectedId] = React.useState("synth");
  const [values, setValues] = React.useState<Record<string, Record<string, unknown>>>({});
  const [advOpen, setAdvOpen] = React.useState(false);
  const [resultOpen, setResultOpen] = React.useState(true);
  const [running, setRunning] = React.useState(false);
  const [results, setResults] = React.useState<Record<string, SurfaceRunResult>>({});
  const [dispatched, setDispatched] = React.useState<Record<string, boolean>>({});
  const rightBodyRef = React.useRef<HTMLDivElement>(null);
  const centerRef = React.useRef<HTMLDivElement>(null);

  // Esc closes (window-level while open; no global shortcut registration).
  React.useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, setOpen]);

  const ctx: SurfaceCtx = React.useMemo(() => ({ manifest, runs }), [manifest, runs]);

  if (!open || !currentSession) return null;

  const cmd = surfaceCommand(selectedId) ?? SURFACE_COMMANDS[0];
  const Icon = iconFor(cmd.id);

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

  const setValue = (key: string, v: unknown) =>
    setValues((prev) => ({
      ...prev,
      [cmd.id]: { ...(prev[cmd.id] ?? {}), [key]: v },
    }));

  const visible = cmd.params.filter((p) => !p.when || p.when(merged));
  const basic = visible.filter((p) => !p.adv);
  const advanced = visible.filter((p) => p.adv);

  const missingRun = visible.some(
    (p) =>
      p.source === "run" &&
      !p.optional &&
      resolveOptions(p, ctx).filter((o) => o !== "").length === 0
  );

  const result = results[cmd.id];
  const wasDispatched = dispatched[cmd.id];

  const invoke = async () => {
    if (running || missingRun) return;
    setRunning(true);
    setDispatched((prev) => ({ ...prev, [cmd.id]: false }));
    try {
      // Pass only the user-touched values — runSurfaceCommand merges defaults.
      const res = await runSurfaceCommand(cmd, userVals);
      if (res === null) {
        // Core command delegated to runCommand — observable in Activity/Runs.
        setDispatched((prev) => ({ ...prev, [cmd.id]: true }));
      } else {
        setResults((prev) => ({ ...prev, [cmd.id]: res }));
        setResultOpen(true);
      }
    } finally {
      setRunning(false);
    }
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
          {/* Left rail — grouped command list */}
          <div className="w-[210px] shrink-0 overflow-y-auto border-r border-border bg-surface-0 py-1.5">
            {SURFACE_GROUPS.map((group) => {
              const members = SURFACE_COMMANDS.filter((c) => c.group === group);
              if (members.length === 0) return null;
              return (
                <div key={group}>
                  <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                    {group}
                  </div>
                  {members.map((c) => {
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

              {cmd.autoArgs && cmd.autoArgs.length > 0 && (
                <div className="mt-4 rounded-lg border border-info/25 bg-info/5 p-3">
                  <div className="mb-2 flex items-center gap-1.5">
                    <Info className="h-3.5 w-3.5 text-info" aria-hidden />
                    <span className="text-[11px] font-semibold text-info">
                      Supplied by manifest — not asked of the user
                    </span>
                  </div>
                  <div className="space-y-1">
                    {cmd.autoArgs.map((a) => (
                      <div key={a.key} className="flex gap-2 font-mono text-[11px]">
                        <span className="w-28 shrink-0 text-muted-foreground">{a.key}</span>
                        <span className="min-w-0 flex-1 break-words text-foreground">
                          {a.describe(ctx)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {basic.length === 0 && advanced.length === 0 && !cmd.autoArgs?.length && (
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
                      value={merged[p.key]}
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
                        value={merged[p.key]}
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

              {result && (
                <div className="mt-3 border-t border-border pt-2">
                  <Collapsible
                    title="Result"
                    tint={result.ok ? "text-status-pass" : "text-status-fail"}
                    open={resultOpen}
                    onToggle={() => setResultOpen((o) => !o)}
                  >
                    {typeof result.result === "string" ? (
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
              <Button
                type="button"
                data-testid="command-surface-invoke"
                className="h-9 w-full gap-1.5 text-xs"
                disabled={running || missingRun}
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
              {wasDispatched && (
                <p className="text-[10px] text-muted-foreground">
                  Dispatched — follow it in Activity/Runs
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default CommandSurface;
