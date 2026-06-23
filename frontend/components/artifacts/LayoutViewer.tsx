"use client";

import { useEffect, useRef, useState } from "react";
import { Layout as LayoutIcon, Loader2, CheckCircle2, Download, Maximize2, ZoomIn, ZoomOut } from "lucide-react";
import { useStore } from "@/lib/store";
import { workspaceApi } from "@/lib/api";
import { getApiBase } from "@/lib/runtime-config";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/workbench/EmptyState";
import { cn } from "@/lib/utils";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

/** A render result that isn't an SVG — the GDS exists but can't be drawn here. */
interface FallbackState {
  kind: string; // unsupported | too_large | render_failed | sidecar | ...
  message?: string;
}

export function LayoutViewer() {
  const { currentSession, layoutFiles, selectedLayout, selectLayout, runs, selectedSynthesisRunId } = useStore();
  const [svgContent, setSvgContent] = useState<string | null>(null);
  const [cellName, setCellName] = useState<string>("");
  const [polygonCount, setPolygonCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [fallback, setFallback] = useState<FallbackState | null>(null);
  const [hardError, setHardError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);

  // PPA for the success card: prefer the selected synth run, else newest synth.
  const synthRuns = runs.filter((r) => r.kind === "synth");
  const ppaRun =
    synthRuns.find((r) => r.id === selectedSynthesisRunId) ?? synthRuns[0];
  const ppa = ppaRun?.ppa;

  useEffect(() => {
    if (currentSession && selectedLayout) {
      loadLayout(selectedLayout);
    } else if (!selectedLayout && layoutFiles.length > 0) {
      selectLayout(layoutFiles[0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedLayout, currentSession]);

  const loadLayout = async (filename: string) => {
    if (!currentSession) return;
    setLoading(true);
    setHardError(null);
    setFallback(null);
    setZoom(1);
    try {
      const data = await workspaceApi.getLayout(currentSession.id, filename);
      // A fallback (unsupported/too_large/render_failed/sidecar) means the GDS
      // EXISTS but can't be drawn here — that is SUCCESS, not failure.
      if ((data as any).error || !data.svg) {
        setSvgContent(null);
        setCellName((data as any).cell_name || "");
        setFallback({ kind: (data as any).error || "no_render", message: (data as any).message });
        return;
      }
      setSvgContent(data.svg);
      setCellName(data.cell_name || "");
      setPolygonCount(typeof (data as any).polygon_count === "number" ? (data as any).polygon_count : null);
    } catch (err) {
      // Network/HTTP failure to even reach the endpoint — a genuine error.
      setSvgContent(null);
      setHardError(err instanceof Error ? err.message : "Failed to load layout");
    } finally {
      setLoading(false);
    }
  };

  if (layoutFiles.length === 0) {
    return (
      <EmptyState
        icon={<LayoutIcon />}
        headline="No layout yet"
        assistantHint="…or ask the assistant to run synthesis for you."
      >
        Run synthesis to generate the GDS layout — it will appear here once the
        flow completes.
      </EmptyState>
    );
  }

  const fileBase = (selectedLayout || layoutFiles[0] || "").split("/").pop() || "layout.gds";

  const handleDownload = async () => {
    if (!currentSession) return;
    const path = selectedLayout || layoutFiles[0];
    try {
      const { content } = await workspaceApi.getFile(currentSession.id, path);
      // Backend returns the GDS bytes as a latin-1/raw string in JSON; map each
      // char code back to a byte for a faithful binary download.
      const bytes = new Uint8Array(content.length);
      for (let i = 0; i < content.length; i++) bytes[i] = content.charCodeAt(i) & 0xff;
      const blob = new Blob([bytes], { type: "application/octet-stream" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = fileBase;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // Best-effort: open the raw endpoint in a new tab as a fallback.
      window.open(`${getApiBase()}/api/workspace/${encodeURIComponent(currentSession.id)}/file/${encodeURIComponent(path)}`, "_blank");
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 p-3 border-b border-border bg-surface-1">
        <LayoutIcon className="h-4 w-4 text-muted-foreground" />
        <Select value={selectedLayout || layoutFiles[0]} onValueChange={selectLayout}>
          <SelectTrigger className="flex-1 h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {layoutFiles.map((file) => (
              <SelectItem key={file} value={file} className="text-xs">
                {file.split("/").pop()}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {cellName && (
          <span className="text-xs text-muted-foreground px-2 py-1 bg-surface-2 rounded">{cellName}</span>
        )}
        {/* Zoom controls — only meaningful when an SVG is rendered. */}
        {svgContent && !loading && (
          <div className="flex items-center gap-0.5">
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              aria-label="Zoom out"
              onClick={() => setZoom((z) => Math.max(0.25, +(z - 0.25).toFixed(2)))}
            >
              <ZoomOut className="h-3.5 w-3.5" />
            </Button>
            <span className="text-[10px] font-mono tabular-nums text-muted-foreground w-9 text-center">
              {Math.round(zoom * 100)}%
            </span>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              aria-label="Zoom in"
              onClick={() => setZoom((z) => Math.min(8, +(z + 0.25).toFixed(2)))}
            >
              <ZoomIn className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              aria-label="Fit to window"
              onClick={() => setZoom(1)}
            >
              <Maximize2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto thin-scrollbar">
        {loading && (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        )}

        {/* Genuine error reaching the endpoint */}
        {hardError && !loading && (
          <div className="flex flex-col items-center justify-center h-full text-muted-foreground p-8 text-center">
            <p className="text-sm font-medium">Couldn&apos;t load the layout</p>
            <p className="text-xs mt-1 max-w-[320px]">{hardError}</p>
            <Button
              variant="outline"
              size="sm"
              className="mt-4"
              onClick={() => selectedLayout && loadLayout(selectedLayout)}
            >
              Retry
            </Button>
          </div>
        )}

        {/* GDS exists but can't be rendered here — SUCCESS card, not an error */}
        {fallback && !loading && !hardError && (
          <div className="flex flex-col items-center justify-center h-full p-8 text-center animate-fade-in">
            <div className="w-16 h-16 rounded-2xl bg-status-pass/15 flex items-center justify-center mb-4">
              <CheckCircle2 className="h-8 w-8 text-status-pass" />
            </div>
            <p className="text-sm font-semibold text-foreground">GDS ready</p>
            <p className="text-xs mt-1 text-muted-foreground max-w-[360px]">
              The layout was generated successfully. An inline preview isn&apos;t
              available for this file
              {fallback.message ? ` (${fallback.message})` : ""}
              {" "}— download it to open in your layout viewer.
            </p>
            {ppa && (
              <div className="mt-4 flex items-center gap-2 text-[11px] font-mono text-muted-foreground">
                {ppa.areaUm2 != null && (
                  <span className="px-2 py-1 rounded bg-surface-2">{ppa.areaUm2.toFixed(2)} µm²</span>
                )}
                {ppa.cells != null && (
                  <span className="px-2 py-1 rounded bg-surface-2">{ppa.cells} cells</span>
                )}
                {cellName && <span className="px-2 py-1 rounded bg-surface-2">{cellName}</span>}
              </div>
            )}
            <Button size="sm" className="mt-4 gap-2" onClick={handleDownload}>
              <Download className="h-4 w-4" />
              Download {fileBase}
            </Button>
          </div>
        )}

        {/* Rendered SVG with zoom */}
        {svgContent && !loading && !hardError && !fallback && (
          <div className="p-4 bg-white dark:bg-surface-0 min-h-full flex items-start justify-center">
            <ZoomableSvg svg={svgContent} zoom={zoom} />
          </div>
        )}
      </div>

      {/* Footer: polygon count + download for rendered layouts */}
      {svgContent && !loading && !fallback && (
        <div className="flex items-center gap-3 px-3 py-1.5 border-t border-border bg-surface-1 text-[11px] text-muted-foreground">
          {polygonCount != null && <span className="font-mono tabular-nums">{polygonCount.toLocaleString()} polygons</span>}
          {ppa?.areaUm2 != null && <span className="font-mono tabular-nums">{ppa.areaUm2.toFixed(2)} µm²</span>}
          <button
            type="button"
            onClick={handleDownload}
            className="ml-auto flex items-center gap-1 text-info hover:underline rounded outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
          >
            <Download className="h-3 w-3" /> Download {fileBase}
          </button>
        </div>
      )}
    </div>
  );
}

/** Renders the inline SVG and applies a CSS zoom transform (scroll to pan). */
function ZoomableSvg({ svg, zoom }: { svg: string; zoom: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const svgEl = el.querySelector("svg");
    if (svgEl) {
      svgEl.style.maxWidth = "100%";
      svgEl.style.height = "auto";
    }
  }, [svg]);
  return (
    <div
      ref={ref}
      className={cn("origin-top transition-transform duration-base ease-swift motion-reduce:transition-none")}
      style={{ transform: `scale(${zoom})` }}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
