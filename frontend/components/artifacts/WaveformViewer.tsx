"use client";

import { useEffect, useState, useRef } from "react";
import { Activity, RefreshCw, ZoomIn, ZoomOut } from "lucide-react";
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

export function WaveformViewer() {
  const {
    waveformFiles,
    selectedWaveform,
    waveformData,
    loadWaveforms,
    selectWaveform,
    currentSession,
  } = useStore();
  const [zoom, setZoom] = useState(1);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (currentSession) {
      loadWaveforms();
    }
  }, [currentSession, loadWaveforms]);

  if (waveformFiles.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
        <Activity className="h-12 w-12 mb-4" />
        <p className="text-sm">No waveforms yet</p>
        <p className="text-xs mt-1">
          Run simulation to generate VCD waveforms
        </p>
      </div>
    );
  }

  const renderSignal = (signal: { name: string; times: number[]; values: number[] }, idx: number) => {
    if (!waveformData) return null;

    const width = 800 * zoom;
    const height = 30;
    const endtime = waveformData.endtime || 1000;
    const scale = width / endtime;
    const maxVal = Math.max(...signal.values, 1);
    const isBus = maxVal > 1;

    return (
      <div key={signal.name} className="flex items-center border-b border-border">
        <div className="w-32 flex-shrink-0 px-2 py-1 bg-muted/30 text-xs font-mono truncate">
          {signal.name}
        </div>
        <svg width={width} height={height} className="flex-shrink-0">
          {isBus ? (
            // Bus display
            <>
              <line x1={0} y1={5} x2={width} y2={5} stroke="currentColor" strokeWidth={1} className="text-muted-foreground/50" />
              <line x1={0} y1={height - 5} x2={width} y2={height - 5} stroke="currentColor" strokeWidth={1} className="text-muted-foreground/50" />
              {signal.times.map((time, i) => {
                const x = time * scale;
                const nextX = i < signal.times.length - 1 ? signal.times[i + 1] * scale : width;
                const val = signal.values[i];
                return (
                  <g key={i}>
                    <line x1={x} y1={5} x2={x} y2={height - 5} stroke="currentColor" strokeWidth={1} className="text-primary" />
                    {nextX - x > 20 && (
                      <text
                        x={x + (nextX - x) / 2}
                        y={height / 2 + 4}
                        textAnchor="middle"
                        className="text-[9px] fill-current"
                      >
                        {val.toString(16).toUpperCase()}
                      </text>
                    )}
                  </g>
                );
              })}
            </>
          ) : (
            // Single-bit display
            <path
              d={signal.times.reduce((path, time, i) => {
                const x = time * scale;
                const y = signal.values[i] ? 5 : height - 5;
                if (i === 0) return `M ${x} ${y}`;
                const prevY = signal.values[i - 1] ? 5 : height - 5;
                return `${path} L ${x} ${prevY} L ${x} ${y}`;
              }, "") + ` L ${width} ${signal.values[signal.values.length - 1] ? 5 : height - 5}`}
              stroke="currentColor"
              strokeWidth={1.5}
              fill="none"
              className="text-primary"
            />
          )}
        </svg>
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Select
            value={selectedWaveform || ""}
            onValueChange={selectWaveform}
          >
            <SelectTrigger className="h-8 w-[200px]">
              <Activity className="h-4 w-4 mr-2" />
              <SelectValue placeholder="Select VCD file" />
            </SelectTrigger>
            <SelectContent>
              {waveformFiles.map((file) => (
                <SelectItem key={file} value={file}>
                  {file}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))}
          >
            <ZoomOut className="h-3.5 w-3.5" />
          </Button>
          <span className="text-xs text-muted-foreground w-12 text-center">
            {Math.round(zoom * 100)}%
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => setZoom((z) => Math.min(4, z + 0.25))}
          >
            <ZoomIn className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => loadWaveforms()}
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Waveform display */}
      <ScrollArea className="flex-1">
        <div ref={containerRef} className="min-w-full">
          {waveformData ? (
            <div className="overflow-x-auto">
              {waveformData.signals.map((signal, idx) =>
                renderSignal(signal, idx)
              )}
              {waveformData.signals.length === 0 && (
                <div className="p-4 text-sm text-muted-foreground text-center">
                  No signals found in waveform
                </div>
              )}
            </div>
          ) : selectedWaveform ? (
            <div className="p-4 text-sm text-muted-foreground text-center">
              Loading waveform...
            </div>
          ) : (
            <div className="p-4 text-sm text-muted-foreground text-center">
              Select a VCD file to view
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Time axis info */}
      {waveformData && (
        <div className="p-2 border-t border-border text-xs text-muted-foreground">
          End time: {waveformData.endtime} ns | {waveformData.signals.length} signals
        </div>
      )}
    </div>
  );
}
