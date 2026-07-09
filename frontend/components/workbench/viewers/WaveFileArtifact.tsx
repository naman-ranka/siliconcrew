"use client";

import { useEffect } from "react";
import { useStore } from "@/lib/store";
import { WaveformViewer } from "@/components/artifacts/WaveformViewer";
import type { WaveformData } from "@/types";
import { ViewerError, ViewerSkeleton } from "./panels";

/**
 * v2 tab wrapper for `wavefile:<path>` — a loose workspace VCD (not produced
 * by a tracked run), parsed through the same backend endpoint and rendered by
 * the same WaveformViewer as run waveforms. No run context line and no failure
 * cursor (there is no run to scope one to) — honest about what we know.
 */
export function WaveFileArtifact({ path }: { path: string }) {
  const slice = useStore((s) => s.artifactCache[`wavefile:${path}`]);
  const loadWaveformFileArtifact = useStore((s) => s.loadWaveformFileArtifact);
  const sessionId = useStore((s) => s.currentSession?.id ?? null);

  useEffect(() => {
    if (sessionId) void loadWaveformFileArtifact(path);
  }, [sessionId, path, loadWaveformFileArtifact]);

  const data = (slice?.data ?? null) as WaveformData | null;

  if (!data) {
    if (slice?.status === "error") {
      return (
        <ViewerError
          title="Couldn't load the waveform"
          detail={slice.error}
          onRetry={() => void loadWaveformFileArtifact(path)}
        />
      );
    }
    return <ViewerSkeleton />;
  }

  return (
    <div className="flex flex-col h-full min-h-0" data-testid="wavefile-artifact">
      <div className="flex items-center gap-2 h-7 px-3 border-b border-border bg-surface-1 shrink-0 text-[11px] font-mono">
        <span className="truncate text-foreground">{path}</span>
        {slice?.status === "revalidating" && (
          <span className="ml-auto shrink-0 text-muted-foreground/70">refreshing…</span>
        )}
      </div>
      <div className="flex-1 min-h-0">
        <WaveformViewer data={data} />
      </div>
    </div>
  );
}
