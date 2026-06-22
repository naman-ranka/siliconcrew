"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, RefreshCw, ZoomIn, ZoomOut, ChevronRight, ChevronDown, Crosshair } from "lucide-react";
import { useStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { WaveformSignal } from "@/types";

const NAME_COL = 168; // px
const LANE_H = 26;

export function WaveformViewer() {
  const {
    waveformFiles,
    selectedWaveform,
    waveformData,
    loadWaveforms,
    selectWaveform,
    currentSession,
    runs,
    selectedRunId,
  } = useStore();
  const [zoom, setZoom] = useState(1);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [manualCursor, setManualCursor] = useState<number | null>(null); // ticks; user-placed
  const [radix, setRadix] = useState<"hex" | "dec">("hex");

  // reset a user-dropped cursor when the waveform changes
  useEffect(() => {
    setManualCursor(null);
  }, [selectedWaveform]);

  useEffect(() => {
    if (currentSession) loadWaveforms();
  }, [currentSession, loadWaveforms]);

  // Keep the waveform in sync with the selected sim run, so opening the Wave tab
  // for an existing/reloaded run shows its isolated VCD without an extra click.
  // Only auto-loads when nothing is selected yet — respects a manual VCD choice.
  useEffect(() => {
    const run = runs.find((r) => r.id === selectedRunId);
    if (run?.kind === "sim" && run.vcdPath && !selectedWaveform) {
      void selectWaveform(run.vcdPath);
    }
  }, [selectedRunId, runs, selectedWaveform, selectWaveform]);

  // The selected sim run pins the failure time → a red cursor in the waveform,
  // so a user can see *when* it went wrong without reading the log.
  const cursorTime = useMemo(() => {
    const run = runs.find((r) => r.id === selectedRunId);
    return run?.kind === "sim" && run.failure?.timeNs != null ? run.failure.timeNs : null;
  }, [runs, selectedRunId]);

  const options = useMemo(
    () => Array.from(new Set([...(selectedWaveform ? [selectedWaveform] : []), ...waveformFiles])),
    [selectedWaveform, waveformFiles]
  );

  // Group signals by scope, preserving the hierarchy-aware order from the API.
  const groups = useMemo(() => {
    const map = new Map<string, WaveformSignal[]>();
    for (const s of waveformData?.signals ?? []) {
      const scope = s.scope || "(top)";
      if (!map.has(scope)) map.set(scope, []);
      map.get(scope)!.push(s);
    }
    return Array.from(map.entries());
  }, [waveformData]);

  // Parse the testbench's failure line ("y=251 expected 5 …") so we can flag the
  // offending signal and show expected-vs-actual — the #1 ask of a failure view.
  // (Declared before any early return so hook order stays stable.)
  const failInfo = useMemo(() => {
    const run = runs.find((r) => r.id === selectedRunId);
    const line = run?.kind === "sim" ? run.failure?.firstFailureLine : null;
    if (!line) return null;
    const m = line.match(/([A-Za-z_]\w*)\s*=\s*(\w+)\s+expected\s+(\w+)/i);
    return m ? { signal: m[1], actual: m[2], expected: m[3] } : null;
  }, [runs, selectedRunId]);

  if (options.length === 0 && !waveformData) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
        <Activity className="h-12 w-12 mb-4" />
        <p className="text-sm">No waveforms yet</p>
        <p className="text-xs mt-1">Run simulation to generate VCD waveforms</p>
      </div>
    );
  }

  const endtime = waveformData?.endtime || 1000;
  const laneWidth = Math.max(600, 800 * zoom);
  const END_PAD = 28; // breathing room so an end-of-sim cursor isn't flush to the edge
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

  const fmtBus = (value: number, isX: boolean, raw?: string): string => {
    if (isX) return (raw ?? "x").toUpperCase();
    return radix === "hex" ? "0x" + value.toString(16).toUpperCase() : String(value);
  };

  // Value of a signal at the active cursor (last change at or before that tick).
  const valueAtCursor = (signal: WaveformSignal): string | null => {
    if (activeCursor == null) return null;
    let idx = -1;
    for (let i = 0; i < signal.times.length; i++) {
      if (signal.times[i] <= activeCursor) idx = i;
      else break;
    }
    if (idx < 0) return null;
    if (signal.xFlags?.[idx]) return (signal.valuesStr?.[idx] ?? "x").toUpperCase();
    return (signal.width ?? 1) > 1 ? fmtBus(signal.values[idx], false) : String(signal.values[idx]);
  };

  // ns label for a tick position (inverse of toTicks), for the cursor readout.
  const ticksToNs = (ticks: number) => (secPerTick && secPerTick < 1 ? (ticks * secPerTick) / 1e-9 : ticks);

  const toggle = (scope: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(scope) ? next.delete(scope) : next.add(scope);
      return next;
    });

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
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Select value={selectedWaveform || ""} onValueChange={selectWaveform}>
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
          {/* radix toggle for buses */}
          <div className="flex rounded-md border border-border overflow-hidden mr-1" role="group" aria-label="Bus radix">
            {(["hex", "dec"] as const).map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => setRadix(r)}
                aria-pressed={radix === r}
                className={cn(
                  "px-1.5 py-0.5 text-[10px] font-mono uppercase",
                  radix === r ? "bg-surface-3 text-foreground" : "text-muted-foreground hover:bg-surface-2"
                )}
              >
                {r}
              </button>
            ))}
          </div>
          <Button variant="ghost" size="icon" className="h-7 w-7" title="Zoom out" aria-label="Zoom out" onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))}>
            <ZoomOut className="h-3.5 w-3.5" />
          </Button>
          <span className="text-xs text-muted-foreground w-12 text-center">{Math.round(zoom * 100)}%</span>
          <Button variant="ghost" size="icon" className="h-7 w-7" title="Zoom in" aria-label="Zoom in" onClick={() => setZoom((z) => Math.min(4, z + 0.25))}>
            <ZoomIn className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7" title="Refresh" aria-label="Refresh waveforms" onClick={() => loadWaveforms()}>
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Waveform display */}
      <ScrollArea className="flex-1">
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
              className="relative"
              onClick={(e) => {
                const x = e.clientX - e.currentTarget.getBoundingClientRect().left - NAME_COL;
                if (x < 0) return; // clicked in the name column
                setManualCursor(Math.min(Math.max(0, x / scale), endtime));
              }}
              title="Click to place a measurement cursor"
            >
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
              {/* user-placed measurement cursor (blue) */}
              {manualCursor != null && activeX != null && (
                <div
                  className="absolute top-0 bottom-0 w-px bg-info z-20 pointer-events-none"
                  style={{ left: NAME_COL + activeX }}
                >
                  <span className="absolute top-0 left-1 text-[9px] text-info font-mono bg-background/80 px-1 rounded">
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
                      className="flex items-center gap-1 w-full px-2 py-1 bg-surface-2/60 hover:bg-surface-2 border-b border-border text-left"
                    >
                      {isCollapsed ? <ChevronRight className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                      <span className="text-[10px] font-mono text-info truncate">{scope}</span>
                      <span className="text-[9px] text-muted-foreground">({sigs.length})</span>
                    </button>
                    {!isCollapsed &&
                      sigs.map((signal) => {
                        const vAtCursor = valueAtCursor(signal);
                        const isCulprit = failInfo != null && signal.name === failInfo.signal;
                        return (
                          <div
                            key={signal.full_name}
                            className={cn(
                              "flex items-center border-b border-border/60 hover:bg-surface-1",
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
                              {vAtCursor != null && (
                                <span
                                  className={cn(
                                    "ml-auto text-[10px] font-semibold tabular-nums",
                                    isCulprit ? "text-status-fail" : "text-info"
                                  )}
                                  title="value at the active cursor"
                                >
                                  ={vAtCursor}
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
