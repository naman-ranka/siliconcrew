"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, RefreshCw, ZoomIn, ZoomOut, ChevronRight, ChevronDown, Crosshair } from "lucide-react";
import { useStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
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
  const scale = laneWidth / endtime;

  // The failure time is in ns; VCD lanes are in the dump's own ticks (ps when
  // the TB declares `timescale 1ns/1ps`, else raw ~ns). Convert via unitSeconds
  // so the cursor lands at the real failure point, not pinned at x=0.
  const secPerTick = waveformData?.unitSeconds ?? null;
  const cursorTicks =
    cursorTime == null
      ? null
      : secPerTick && secPerTick < 1
      ? (cursorTime * 1e-9) / secPerTick
      : cursorTime;
  const clampedCursor = cursorTicks == null ? null : Math.min(Math.max(0, cursorTicks), endtime);
  const cursorX = clampedCursor != null ? clampedCursor * scale : null;

  // Value of a signal at the cursor (last change at or before the cursor tick) —
  // lets a user read the offending value (e.g. count=20) right at the failure.
  const valueAtCursor = (signal: WaveformSignal): string | null => {
    if (clampedCursor == null) return null;
    let idx = -1;
    for (let i = 0; i < signal.times.length; i++) {
      if (signal.times[i] <= clampedCursor) idx = i;
      else break;
    }
    if (idx < 0) return null;
    if (signal.xFlags?.[idx]) return (signal.valuesStr?.[idx] ?? "x").toUpperCase();
    return (signal.width ?? 1) > 1 ? "0x" + signal.values[idx].toString(16).toUpperCase() : String(signal.values[idx]);
  };

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
              : signal.values[i].toString(16).toUpperCase();
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
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))}>
            <ZoomOut className="h-3.5 w-3.5" />
          </Button>
          <span className="text-xs text-muted-foreground w-12 text-center">{Math.round(zoom * 100)}%</span>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setZoom((z) => Math.min(4, z + 0.25))}>
            <ZoomIn className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => loadWaveforms()}>
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

            <div className="relative">
              {/* failure cursor across all lanes */}
              {cursorX != null && (
                <div
                  className="absolute top-0 bottom-0 w-px bg-status-fail z-20 pointer-events-none"
                  style={{ left: NAME_COL + cursorX }}
                >
                  <span className="absolute -top-0 left-1 text-[9px] text-status-fail font-mono bg-background/80 px-1 rounded">
                    {cursorTime}ns
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
                        return (
                          <div key={signal.full_name} className="flex items-center border-b border-border/60 hover:bg-surface-1">
                            <div
                              style={{ width: NAME_COL }}
                              className="shrink-0 px-2 py-1 text-xs font-mono flex items-center gap-1"
                              title={signal.full_name}
                            >
                              <span className="truncate">{signal.name}</span>
                              {(signal.width ?? 1) > 1 && (
                                <span className="text-[9px] text-muted-foreground">[{signal.width}]</span>
                              )}
                              {vAtCursor != null && (
                                <span
                                  className="ml-auto text-[10px] text-info font-semibold tabular-nums"
                                  title={`value at cursor (${cursorTime}ns)`}
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
