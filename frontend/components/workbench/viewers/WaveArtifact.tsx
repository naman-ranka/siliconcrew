"use client";

import { useEffect } from "react";
import { Activity } from "lucide-react";
import { useStore } from "@/lib/store";
import { WaveformViewer } from "@/components/artifacts/WaveformViewer";
import { cn } from "@/lib/utils";
import type { WaveformData } from "@/types";
import { ViewerEmpty, ViewerError, ViewerSkeleton } from "./panels";

const STATUS_CHIP: Record<string, string> = {
  passed: "bg-status-pass/15 text-status-pass",
  failed: "bg-status-fail/15 text-status-fail",
  running: "bg-status-running/15 text-status-running",
};

/**
 * v2 tab wrapper for `wave:<runId>` — loads the run's VCD through the store's
 * artifact cache (terminal runs cache forever) and renders the existing
 * WaveformViewer with its data-override prop.
 */
export function WaveArtifact({ runId }: { runId: string }) {
  const runs = useStore((s) => s.runs);
  const slice = useStore((s) => s.artifactCache[`wave:${runId}`]);
  const loadWaveformArtifact = useStore((s) => s.loadWaveformArtifact);
  const sessionId = useStore((s) => s.currentSession?.id ?? null);

  const run = runs.find((r) => r.id === runId);
  const vcdPath = run?.vcdPath;

  useEffect(() => {
    if (sessionId && vcdPath) void loadWaveformArtifact(runId, vcdPath);
  }, [sessionId, runId, vcdPath, loadWaveformArtifact]);

  if (!run || !vcdPath) {
    return (
      <ViewerEmpty
        icon={<Activity />}
        title="No waveform for this run"
        detail={
          run
            ? "This run produced no VCD dump — add $dumpvars to the testbench and re-run."
            : `Run ${runId} isn't in the run list (it may have been cleaned up).`
        }
      />
    );
  }

  const data = (slice?.data ?? null) as WaveformData | null;

  if (!data) {
    if (slice?.status === "error") {
      return (
        <ViewerError
          title="Couldn't load the waveform"
          detail={slice.error}
          onRetry={() => void loadWaveformArtifact(runId, vcdPath)}
        />
      );
    }
    return <ViewerSkeleton />;
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Run context line */}
      <div className="flex items-center gap-2 h-7 px-3 border-b border-border bg-surface-1 shrink-0 text-[11px] font-mono">
        <span className="text-foreground">{run.id}</span>
        <span
          className={cn(
            "px-1.5 py-px rounded uppercase tracking-wider text-[9px] font-semibold",
            STATUS_CHIP[run.status] ?? "bg-surface-2 text-muted-foreground"
          )}
        >
          {run.status}
        </span>
        {run.top && <span className="text-muted-foreground truncate">{run.top}</span>}
        {slice?.status === "revalidating" && (
          <span className="ml-auto text-muted-foreground/70">refreshing…</span>
        )}
      </div>
      <div className="flex-1 min-h-0">
        <WaveformViewer data={data} runId={runId} />
      </div>
    </div>
  );
}
