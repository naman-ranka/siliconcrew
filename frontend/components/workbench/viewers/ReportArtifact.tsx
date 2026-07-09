"use client";

import { useEffect } from "react";
import { useStore } from "@/lib/store";
import { ReportViewer } from "@/components/artifacts/ReportViewer";
import { PpaHero } from "@/components/artifacts/PpaHero";
import type { ReportData } from "@/types";
import { ViewerError, ViewerSkeleton, ViewerSpinner } from "./panels";

/**
 * v2 tab wrapper for `report:<runId>` — loads the run's report through the
 * store's artifact cache and renders the existing ReportViewer with its
 * override props (which also renders the PpaHero for that run).
 */
export function ReportArtifact({ runId }: { runId: string }) {
  const runs = useStore((s) => s.runs);
  const slice = useStore((s) => s.artifactCache[`report:${runId}`]);
  const loadReportArtifact = useStore((s) => s.loadReportArtifact);
  const sessionId = useStore((s) => s.currentSession?.id ?? null);

  const run = runs.find((r) => r.id === runId);
  const running = run?.status === "running";

  useEffect(() => {
    if (sessionId && !running) void loadReportArtifact(runId);
  }, [sessionId, runId, running, loadReportArtifact]);

  if (running) {
    return (
      <ViewerSpinner
        title="Synthesizing…"
        detail={`${runId} is still running — the report appears when the flow finishes.`}
      />
    );
  }

  const data = (slice?.data ?? null) as ReportData | null;

  if (!data) {
    if (slice?.status === "error") {
      // Even without a markdown report, the run record may carry PPA — show it
      // above the honest error so the tab is still useful.
      const hasPpa = run?.kind === "synth" && run.ppa != null;
      return (
        <div className="flex flex-col h-full min-h-0 overflow-y-auto">
          {hasPpa && <PpaHero runs={runs} runId={runId} />}
          <div className="flex-1 min-h-[200px]">
            <ViewerError
              title="No report for this run yet"
              detail={slice.error}
              onRetry={() => void loadReportArtifact(runId)}
            />
          </div>
        </div>
      );
    }
    return <ViewerSkeleton />;
  }

  return <ReportViewer reportOverride={data} runIdOverride={runId} />;
}
