"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Activity, RefreshCw, ZoomIn, ZoomOut, ChevronRight, ChevronDown, Crosshair, Maximize2 } from "lucide-react";
import { useStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { IconTooltip } from "@/components/ui/tooltip";
import { ScrollArea } from "@/components/ui/scroll-area";
import { EmptyState } from "@/components/workbench/EmptyState";
import { cn } from "@/lib/utils";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { WaveformData, WaveformSignal } from "@/types";

const NAME_COL = 168; // px
const LANE_H = 26;
const BASE_LANE = 800; // px of lane width at 100% zoom
const MIN_LANE = 600;
const END_PAD = 28; // breathing room so an end-of-sim cursor isn't flush to the edge

interface WaveformViewerProps {
  // v2 tab model: render EXACTLY this waveform (bypasses the store's
  // selectedWaveform/waveformData plumbing). When absent, behavior is the
  // original store-driven viewer, unchanged.
  data?: WaveformData;
  // v2 tab model: scope the failure cursor / culprit highlight to this run
  // instead of the globally selected run. Only used alongside `data`.
  runId?: string;
}

export function WaveformViewer({ data: dataProp, runId: runIdProp }: WaveformViewerProps = {}) {
  const {
    waveformFiles,
    selectedWaveform,
    waveformData: storeWaveformData,
    loadWaveforms,
    selectWaveform,
    currentSession,
    runs,
    selectedRunId,
  } = useStore();
  const overridden = dataProp != null;
  const waveformData = dataProp ?? storeWaveformData;
  // Data-override mode scopes the failure cursor to the caller's run ONLY —
  // a run-less waveform (loose workspace VCD) must never inherit the globally
  // selected run's failure time.
  const effectiveRunId = overridden ? runIdProp ?? null : selectedRunId;
  const [zoom, setZoom] = useState(1);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [manualCursor, setManualCursor] = useState<number | null>(null); // ticks; user-placed
  const [radix, setRadix] = useState<"hex" | "dec">("hex");
  const [hoverTicks, setHoverTicks] = useState<number | null>(null); // ticks; mouse-move scrub
  const [dragging, setDragging] = useState(false);

  // Measure the lane viewport so "Fit" can scale the whole sim to the panel.
  const laneViewportRef = useRef<HTMLDivElement>(null);
  const lanesRef = useRef<HTMLDivElement>(null);

  // Track which run's VCD we auto-loaded, and whether the user has manually
  // overridden the VCD for the *current* selected run. Both are refs so the
  // sync effect doesn't re-run when they change (and never desyncs hook order).
  const syncedRunIdRef = useRef<string | null>(null);
  const manualOverrideRef = useRef(false);
  // Latest clientX→ticks mapper, kept in a ref so the window-bound drag effect
  // (declared before the early return for stable hook order) can use the current
  // scale/endtime without depending on values computed after that return.
  const xToTicksRef = useRef<(clientX: number) => number | null>(() => null);

  // reset a user-dropped cursor / hover when the waveform changes
  // (dataProp is a constant `undefined` in store-driven mode — no-op dep)
  useEffect(() => {
    setManualCursor(null);
    setHoverTicks(null);
  }, [selectedWaveform, dataProp]);

  useEffect(() => {
    if (currentSession && !overridden) loadWaveforms();
  }, [currentSession, loadWaveforms, overridden]);

  // Keep the waveform in sync with the SELECTED sim run. The viewer must follow
  // selectedRunId: when the selected run changes, load THAT run's VCD even if a
  // different VCD is already loaded (the midpoint bug: Wave tab showed sim_0001
  // while the banner viewed sim_0003). A manual dropdown pick overrides until the
  // selected run changes again, at which point the new run's VCD wins.
  useEffect(() => {
    if (overridden) return; // v2: the tab owns its data — never touch the store
    const run = runs.find((r) => r.id === selectedRunId);
    if (!(run?.kind === "sim" && run.vcdPath)) return;
    if (selectedRunId !== syncedRunIdRef.current) {
      // The selected run changed → adopt its VCD and clear any manual override.
      syncedRunIdRef.current = selectedRunId ?? null;
      manualOverrideRef.current = false;
      if (run.vcdPath !== selectedWaveform) void selectWaveform(run.vcdPath);
    } else if (!manualOverrideRef.current && !selectedWaveform) {
      // Same run, nothing loaded yet (e.g. after a refresh) → adopt its VCD.
      void selectWaveform(run.vcdPath);
    }
  }, [selectedRunId, runs, selectedWaveform, selectWaveform, overridden]);

  // Wrap selectWaveform so a manual dropdown pick records the override; the
  // selected run's VCD will reclaim the view once the run changes again.
  const handlePickWaveform = useCallback(
    (file: string) => {
      manualOverrideRef.current = true;
      void selectWaveform(file);
    },
    [selectWaveform]
  );

  // The selected sim run pins the failure time → a red cursor in the waveform,
  // so a user can see *when* it went wrong without reading the log.
  const cursorTime = useMemo(() => {
    const run = runs.find((r) => r.id === effectiveRunId);
    return run?.kind === "sim" && run.failure?.timeNs != null ? run.failure.timeNs : null;
  }, [runs, effectiveRunId]);

  const options = useMemo(
    () =>
      overridden
        ? [dataProp!.filename]
        : Array.from(new Set([...(selectedWaveform ? [selectedWaveform] : []), ...waveformFiles])),
    [selectedWaveform, waveformFiles, overridden, dataProp]
  );

  // Group signals by scope, preserving the hierarchy-aware order from the API.
  // Dedup aliased nets: `$dumpvars` lists a port and its connected net under both
  // `tb` and `tb.dut`, so the same signal renders twice. We collapse a signal
  // when an earlier signal has the same leaf name + identical time/value vector
  // (a true alias), keeping the first (shallowest-scope) occurrence. The culprit
  // highlight + `exp` badge then renders only once.
  const groups = useMemo(() => {
    const seen = new Map<string, WaveformSignal>(); // alias key → kept signal
    const aliasKey = (s: WaveformSignal) =>
      `${s.name}|${(s.width ?? 1)}|${s.times.join(",")}|${s.values.join(",")}`;
    const map = new Map<string, WaveformSignal[]>();
    for (const s of waveformData?.signals ?? []) {
      const key = aliasKey(s);
      if (seen.has(key)) continue; // duplicate net under a different scope — drop it
      seen.set(key, s);
      const scope = s.scope || "(top)";
      if (!map.has(scope)) map.set(scope, []);
      map.get(scope)!.push(s);
    }
    return Array.from(map.entries()).filter(([, sigs]) => sigs.length > 0);
  }, [waveformData]);

  // Parse the testbench's failure line ("y=251 expected 5 …") so we can flag the
  // offending signal and show expected-vs-actual — the #1 ask of a failure view.
  // (Declared before any early return so hook order stays stable.)
  const failInfo = useMemo(() => {
    const run = runs.find((r) => r.id === effectiveRunId);
    const line = run?.kind === "sim" ? run.failure?.firstFailureLine : null;
    if (!line) return null;
    const m = line.match(/([A-Za-z_]\w*)\s*=\s*(\w+)\s+expected\s+(\w+)/i);
    return m ? { signal: m[1], actual: m[2], expected: m[3] } : null;
  }, [runs, effectiveRunId]);

  // Dragging the cursor handle: bind window listeners so the drag keeps tracking
  // even when the pointer leaves the lane host. Declared before any early return
  // to keep hook order stable; reads the live mapper via xToTicksRef.
  useEffect(() => {
    if (!dragging) return;
    const onMove = (e: MouseEvent) => {
      const t = xToTicksRef.current(e.clientX);
      if (t != null) {
        setHoverTicks(t);
        setManualCursor(t);
      }
    };
    const onUp = () => setDragging(false);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [dragging]);

  if (options.length === 0 && !waveformData) {
    return (
      <EmptyState
        icon={<Activity />}
        headline="No waveforms yet"
        assistantHint="…or ask the assistant to write a testbench and simulate."
      >
        Run simulation to generate VCD waveforms from your testbench.
      </EmptyState>
    );
  }

  const endtime = waveformData?.endtime || 1000;
  const laneWidth = Math.max(MIN_LANE, BASE_LANE * zoom);
  const scale = (laneWidth - END_PAD) / endtime;

  // The failure time is in ns; VCD lanes are in the dump's own ticks (ps when
  // the TB declares `timescale 1ns/1ps`, else raw ~ns). Convert via unitSeconds
  // so the cursor lands at the real failure point, not pinned at x=0.
  const secPerTick = waveformData?.unitSeconds ?? null;
  const toTicks = (ns: number) => (secPerTick && secPerTick < 1 ? (ns * 1e-9) / secPerTick : ns);
  const failTicks =
    cursorTime == null ? null : Math.min(Math.max(0, toTicks(cursorTime)), endtime);
  const failX = failTicks != null ? failTicks * scale : null;

  // Active cursor = the user's dropped cursor, else the failure marker.
  const activeCursor = manualCursor != null ? Math.min(Math.max(0, manualCursor), endtime) : failTicks;
  const activeX = activeCursor != null ? activeCursor * scale : null;
  const hoverX = hoverTicks != null ? hoverTicks * scale : null;

  const fmtBus = (value: number, isX: boolean, raw?: string): string => {
    if (isX) return (raw ?? "x").toUpperCase();
    return radix === "hex" ? "0x" + value.toString(16).toUpperCase() : String(value);
  };

  // Value of a signal at a given tick (last change at or before that tick).
  const valueAt = (signal: WaveformSignal, at: number | null): string | null => {
    if (at == null) return null;
    let idx = -1;
    for (let i = 0; i < signal.times.length; i++) {
      if (signal.times[i] <= at) idx = i;
      else break;
    }
    if (idx < 0) return null;
    if (signal.xFlags?.[idx]) return (signal.valuesStr?.[idx] ?? "x").toUpperCase();
    return (signal.width ?? 1) > 1 ? fmtBus(signal.values[idx], false) : String(signal.values[idx]);
  };
  const valueAtCursor = (signal: WaveformSignal): string | null => valueAt(signal, activeCursor);

  // ns label for a tick position (inverse of toTicks), for the cursor readout.
  const ticksToNs = (ticks: number) => (secPerTick && secPerTick < 1 ? (ticks * secPerTick) / 1e-9 : ticks);

  const toggle = (scope: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(scope) ? next.delete(scope) : next.add(scope);
      return next;
    });

  // Map a clientX onto a tick position within the lane area (null if over names).
  const xToTicks = (clientX: number): number | null => {
    const host = lanesRef.current;
    if (!host) return null;
    const x = clientX - host.getBoundingClientRect().left - NAME_COL;
    if (x < 0) return null;
    return Math.min(Math.max(0, x / scale), endtime);
  };
  xToTicksRef.current = xToTicks;

  const handleLanesMove = (e: React.MouseEvent) => {
    const t = xToTicks(e.clientX);
    if (t == null) {
      if (!dragging) setHoverTicks(null);
      return;
    }
    setHoverTicks(t);
    if (dragging) setManualCursor(t);
  };

  // Fit: choose a zoom so the whole sim spans the visible lane viewport width.
  const handleFit = () => {
    const vp = laneViewportRef.current;
    if (!vp) return;
    const avail = vp.clientWidth - NAME_COL;
    if (avail <= 0) return;
    const target = (avail + END_PAD) / BASE_LANE;
    setZoom(Math.min(4, Math.max(0.5, Math.round(target * 100) / 100)));
  };

  const renderLane = (signal: WaveformSignal) => {
    const width = laneWidth;
    const h = LANE_H;
    const isBus = signal.isBus || (signal.width ?? 1) > 1;

    if (isBus) {
      return (
        <svg width={width} height={h} className="block">
          <line x1={0} y1={4} x2={width} y2={4} className="stroke-muted-foreground/40" strokeWidth={1} />
          <line x1={0} y1={h - 4} x2={width} y2={h - 4} className="stroke-muted-foreground/40" strokeWidth={1} />
          {signal.times.map((time, i) => {
            const x = time * scale;
            const nextX = i < signal.times.length - 1 ? signal.times[i + 1] * scale : width;
            const isX = signal.xFlags?.[i];
            const label = isX
              ? (signal.valuesStr?.[i] ?? "x").toUpperCase()
              : radix === "hex"
              ? signal.values[i].toString(16).toUpperCase()
              : String(signal.values[i]);
            return (
              <g key={i}>
                <line x1={x} y1={4} x2={x} y2={h - 4} className="stroke-primary" strokeWidth={1} />
                <rect
                  x={x}
                  y={4}
                  width={Math.max(0, nextX - x)}
                  height={h - 8}
                  className={isX ? "fill-status-fail/15" : "fill-transparent"}
                />
                {nextX - x > 22 && (
                  <text
                    x={x + (nextX - x) / 2}
                    y={h / 2 + 4}
                    textAnchor="middle"
                    className={isX ? "fill-status-fail text-[9px] font-mono" : "fill-foreground text-[9px] font-mono"}
                  >
                    {label}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      );
    }

    // single-bit step waveform, with x/z drawn as a mid red band
    let d = "";
    signal.times.forEach((time, i) => {
      const x = time * scale;
      const y = signal.values[i] ? 5 : h - 5;
      if (i === 0) d = `M ${x} ${y}`;
      else {
        const prevY = signal.values[i - 1] ? 5 : h - 5;
        d += ` L ${x} ${prevY} L ${x} ${y}`;
      }
    });
    const lastY = signal.values[signal.values.length - 1] ? 5 : h - 5;
    d += ` L ${width} ${lastY}`;
    return (
      <svg width={width} height={h} className="block">
        {signal.times.map((time, i) =>
          signal.xFlags?.[i] ? (
            <rect
              key={`x${i}`}
              x={time * scale}
              y={h / 2 - 3}
              width={Math.max(2, (i < signal.times.length - 1 ? signal.times[i + 1] * scale : width) - time * scale)}
              height={6}
              className="fill-status-fail/40"
            />
          ) : null
        )}
        <path d={d} className="stroke-primary" strokeWidth={1.5} fill="none" />
      </svg>
    );
  };

  const tickCount = 8;
  const ticks = Array.from({ length: tickCount + 1 }, (_, i) => Math.round((endtime / tickCount) * i));

  return (
    <div className="flex flex-col h-full" data-testid="waveform-viewer">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-border">
        <div className="flex items-center gap-2">
          {overridden ? (
            <span className="flex items-center gap-2 h-8 px-2 text-xs font-mono text-muted-foreground bg-surface-1 border border-border rounded-md min-w-0">
              <Activity className="h-4 w-4 shrink-0" />
              <span className="truncate max-w-[220px]">
                {dataProp!.filename.includes("/")
                  ? dataProp!.filename.split("/").slice(-2).join("/")
                  : dataProp!.filename}
              </span>
            </span>
          ) : (
          <Select value={selectedWaveform || ""} onValueChange={handlePickWaveform}>
            <SelectTrigger className="h-8 w-[230px]">
              <Activity className="h-4 w-4 mr-2" />
              <SelectValue placeholder="Select VCD file" />
            </SelectTrigger>
            <SelectContent>
              {options.map((file) => (
                <SelectItem key={file} value={file}>
                  {file.includes("/") ? file.split("/").slice(-2).join("/") : file}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          )}
          {cursorTime != null && (
            <span className="flex items-center gap-1 text-[11px] text-status-fail font-mono">
              <Crosshair className="h-3.5 w-3.5" /> fail @ {cursorTime}ns
            </span>
          )}
          {manualCursor != null && (
            <button
              type="button"
              onClick={() => setManualCursor(null)}
              className="text-[11px] text-info font-mono hover:underline"
              title="Clear the placed cursor"
            >
              cursor @ {Math.round(ticksToNs(manualCursor))}ns ✕
            </button>
          )}
        </div>
        <div className="flex items-center gap-1">
          {/* segmented radix control for buses */}
          <div
            className="flex items-center rounded-md border border-border bg-surface-1 p-0.5 mr-1"
            role="group"
            aria-label="Bus radix"
          >
            {(["hex", "dec"] as const).map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => setRadix(r)}
                aria-pressed={radix === r}
                className={cn(
                  "px-2 py-0.5 text-[10px] font-mono uppercase rounded-[3px] transition-colors [transition-duration:var(--dur-fast)] [transition-timing-function:var(--ease)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  radix === r
                    ? "bg-surface-3 text-foreground shadow-e1"
                    : "text-muted-foreground hover:text-foreground hover:bg-surface-2"
                )}
              >
                {r}
              </button>
            ))}
          </div>
          <IconTooltip label="Fit to window">
            <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Fit waveform to window" onClick={handleFit}>
              <Maximize2 className="h-3.5 w-3.5" />
            </Button>
          </IconTooltip>
          <IconTooltip label="Zoom out">
            <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Zoom out" onClick={() => setZoom((z) => Math.max(0.5, Math.round((z - 0.25) * 100) / 100))}>
              <ZoomOut className="h-3.5 w-3.5" />
            </Button>
          </IconTooltip>
          <span className="text-xs text-muted-foreground w-12 text-center tabular-nums">{Math.round(zoom * 100)}%</span>
          <IconTooltip label="Zoom in">
            <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Zoom in" onClick={() => setZoom((z) => Math.min(4, Math.round((z + 0.25) * 100) / 100))}>
              <ZoomIn className="h-3.5 w-3.5" />
            </Button>
          </IconTooltip>
          {!overridden && (
            <IconTooltip label="Refresh waveforms">
              <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Refresh waveforms" onClick={() => loadWaveforms()}>
                <RefreshCw className="h-3.5 w-3.5" />
              </Button>
            </IconTooltip>
          )}
        </div>
      </div>

      {/* Waveform display */}
      <ScrollArea className="flex-1" viewportRef={laneViewportRef}>
        {waveformData ? (
          <div className="min-w-full">
            {/* Time ruler */}
            <div className="flex sticky top-0 z-10 bg-surface-1 border-b border-border">
              <div style={{ width: NAME_COL }} className="shrink-0 px-2 py-1 text-[10px] text-muted-foreground">
                signal
              </div>
              <div className="relative" style={{ width: laneWidth, height: 20 }}>
                {ticks.map((t, i) => (
                  <span
                    key={i}
                    className="absolute text-[9px] text-muted-foreground font-mono"
                    style={{ left: Math.min(laneWidth - 24, t * scale + 2), top: 3 }}
                  >
                    {t}
                  </span>
                ))}
              </div>
            </div>

            <div
              ref={lanesRef}
              className="relative"
              onClick={(e) => {
                const t = xToTicks(e.clientX);
                if (t != null) setManualCursor(t);
              }}
              onMouseMove={handleLanesMove}
              onMouseLeave={() => {
                if (!dragging) setHoverTicks(null);
              }}
              title="Click to place a measurement cursor"
            >
              {/* Faint vertical gridlines aligned to the ruler ticks, behind lanes. */}
              <div className="absolute inset-0 z-0 pointer-events-none" aria-hidden>
                {ticks.map((t, i) => (
                  <div
                    key={i}
                    className="absolute top-0 bottom-0 w-px bg-border/40"
                    style={{ left: NAME_COL + t * scale }}
                  />
                ))}
              </div>

              {/* hover scrub guide (calm, dashed) */}
              {hoverX != null && hoverTicks != null && (
                <div
                  className="absolute top-0 bottom-0 z-20 pointer-events-none border-l border-dashed border-muted-foreground/50"
                  style={{ left: NAME_COL + hoverX }}
                >
                  <span className="absolute top-0 left-1 text-[9px] text-muted-foreground font-mono bg-background/85 px-1 rounded whitespace-nowrap">
                    {Math.round(ticksToNs(hoverTicks))}ns
                  </span>
                </div>
              )}

              {/* failure cursor (red) across all lanes */}
              {failX != null && (
                <div
                  className="absolute top-0 bottom-0 w-px bg-status-fail z-20 pointer-events-none"
                  style={{ left: NAME_COL + failX }}
                >
                  <span className="absolute top-0 left-1 text-[9px] text-status-fail font-mono bg-background/80 px-1 rounded">
                    fail {cursorTime}ns
                  </span>
                </div>
              )}
              {/* user-placed measurement cursor (blue) with a draggable handle */}
              {manualCursor != null && activeX != null && (
                <div
                  className="absolute top-0 bottom-0 w-px bg-info z-30"
                  style={{ left: NAME_COL + activeX }}
                >
                  {/* grab handle to scrub the cursor */}
                  <button
                    type="button"
                    aria-label="Drag measurement cursor"
                    title="Drag to scrub"
                    onMouseDown={(e) => {
                      e.stopPropagation();
                      e.preventDefault();
                      setDragging(true);
                    }}
                    className={cn(
                      "absolute -top-0.5 -translate-x-1/2 h-3 w-3 rounded-sm bg-info border border-background",
                      "cursor-ew-resize shadow-e1 pointer-events-auto",
                      dragging && "ring-2 ring-info/40"
                    )}
                  />
                  <span className="absolute top-3.5 left-1 text-[9px] text-info font-mono bg-background/80 px-1 rounded pointer-events-none">
                    {Math.round(ticksToNs(activeCursor!))}ns
                  </span>
                </div>
              )}

              {groups.map(([scope, sigs]) => {
                const isCollapsed = collapsed.has(scope);
                return (
                  <div key={scope}>
                    <button
                      type="button"
                      onClick={() => toggle(scope)}
                      className="flex items-center gap-1 w-full px-2 py-1 bg-surface-2/60 hover:bg-surface-2 border-b border-border text-left relative z-10"
                    >
                      {isCollapsed ? <ChevronRight className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                      <span className="text-[10px] font-mono text-info truncate">{scope}</span>
                      <span className="text-[9px] text-muted-foreground">({sigs.length})</span>
                    </button>
                    {!isCollapsed &&
                      sigs.map((signal) => {
                        const vAtCursor = valueAtCursor(signal);
                        const vAtHover = hoverTicks != null ? valueAt(signal, hoverTicks) : null;
                        const isCulprit = failInfo != null && signal.name === failInfo.signal;
                        return (
                          <div
                            key={signal.full_name}
                            className={cn(
                              "flex items-center border-b border-border/60 hover:bg-surface-1 relative z-10",
                              isCulprit && "bg-status-fail/10"
                            )}
                          >
                            <div
                              style={{ width: NAME_COL }}
                              className="shrink-0 px-2 py-1 text-xs font-mono flex items-center gap-1"
                              title={signal.full_name}
                            >
                              <span className={cn("truncate", isCulprit && "text-status-fail font-semibold")}>
                                {signal.name}
                              </span>
                              {(signal.width ?? 1) > 1 && (
                                <span className="text-[9px] text-muted-foreground">[{signal.width}]</span>
                              )}
                              {isCulprit && (
                                <span
                                  className="text-[9px] text-status-fail border border-status-fail/40 rounded px-1"
                                  title={`testbench expected ${failInfo!.expected}, got ${failInfo!.actual}`}
                                >
                                  exp {failInfo!.expected}
                                </span>
                              )}
                              {/* hover value takes precedence so scrubbing reads live */}
                              {(vAtHover ?? vAtCursor) != null && (
                                <span
                                  className={cn(
                                    "ml-auto text-[10px] font-semibold tabular-nums",
                                    vAtHover != null
                                      ? "text-muted-foreground"
                                      : isCulprit
                                      ? "text-status-fail"
                                      : "text-info"
                                  )}
                                  title={vAtHover != null ? "value at the hovered time" : "value at the active cursor"}
                                >
                                  ={vAtHover ?? vAtCursor}
                                </span>
                              )}
                            </div>
                            <div className="shrink-0">{renderLane(signal)}</div>
                          </div>
                        );
                      })}
                  </div>
                );
              })}
              {groups.length === 0 && (
                <div className="p-4 text-sm text-muted-foreground text-center">No signals found in waveform</div>
              )}
            </div>
          </div>
        ) : selectedWaveform ? (
          <div className="p-4 text-sm text-muted-foreground text-center">Loading waveform...</div>
        ) : (
          <div className="p-4 text-sm text-muted-foreground text-center">Select a VCD file to view</div>
        )}
      </ScrollArea>

      {/* Footer */}
      {waveformData && (
        <div className="p-2 border-t border-border text-xs text-muted-foreground flex items-center gap-3">
          <span>End: {waveformData.endtime}{waveformData.timescale && /[a-z]/i.test(String(waveformData.timescale)) ? ` ${waveformData.timescale}` : " ns"}</span>
          <span>{waveformData.signalCount ?? waveformData.signals.length} signals</span>
          <span>{groups.length} scopes</span>
        </div>
      )}
    </div>
  );
}
