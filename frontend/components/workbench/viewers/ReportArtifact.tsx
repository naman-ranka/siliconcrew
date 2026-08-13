"use client";

import { useEffect } from "react";
import { Loader2, XCircle } from "lucide-react";
import { useStore } from "@/lib/store";
import { ReportViewer } from "@/components/artifacts/ReportViewer";
import { PpaHero } from "@/components/artifacts/PpaHero";
import type { ReportData } from "@/types";
import { ViewerError, ViewerSkeleton } from "./panels";

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
  const synthJob = useStore((s) => s.synthJob);

  const run = runs.find((r) => r.id === runId);
  const running = run?.status === "running";

  useEffect(() => {
    if (sessionId && !running) void loadReportArtifact(runId);
  }, [sessionId, runId, running, loadReportArtifact]);

  if (running) {
    // Live run (sc#67): render the LAST-KNOWN log tail + the backend's
    // staleness label instead of a bare spinner. The tail lives on the
    // synthJob slice, which is fed only by activity events / the user's
    // Refresh / focus revalidate — the viewer never fetches or polls on its
    // own (invariant 6), so an untracked run honestly says it has no tail.
    const live = synthJob?.runId === runId ? synthJob : null;
    const logLines = live?.lastLogLines?.length ? live.lastLogLines : null;
    return (
      <div className="flex h-full min-h-0 flex-col overflow-y-auto">
        <div className="flex items-start gap-2 p-4 pb-0">
          <Loader2
            className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-muted-foreground"
            aria-hidden
          />
          <div className="min-w-0">
            <p className="text-sm font-medium text-foreground">Synthesizing…</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {runId} is still running — the report appears when the flow finishes.
            </p>
          </div>
        </div>
        <div className="flex-1 space-y-3 p-4">
          {logLines ? (
            <div>
              <p className="mb-1 text-[10px] text-muted-foreground">
                <span className="uppercase tracking-wide">Last log lines</span>
                {live?.lastLogSource ? (
                  // Verbatim backend provenance ("partial (updated Ns ago)" /
                  // "final") — staleness shown, never freshness pretended.
                  <span className="ml-1.5 font-mono">· {live.lastLogSource}</span>
                ) : null}
              </p>
              <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded bg-surface-2 p-2 font-mono text-[11px] text-muted-foreground">
                {logLines.join("\n")}
              </pre>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              No log tail available for this run yet — use Refresh in the Runs panel to pull its
              latest status.
            </p>
          )}
        </div>
      </div>
    );
  }

  const data = (slice?.data ?? null) as ReportData | null;

  if (!data && run?.status === "failed") {
    // Honest failure panel (F12): a failed synth run rarely has a markdown
    // report, but it DOES carry the failing stage + a one-line reason. The
    // log tail exists client-side only when the live synthJob is THIS run —
    // the UI is a viewer (invariant 6), so we never fetch it.
    const hasPpa = run.kind === "synth" && run.ppa != null;
    const logLines =
      synthJob?.runId === runId && synthJob.lastLogLines?.length
        ? synthJob.lastLogLines
        : null;
    return (
      <div className="flex flex-col h-full min-h-0 overflow-y-auto">
        {hasPpa && <PpaHero runs={runs} runId={runId} />}
        <div className="flex-1 min-h-[200px] space-y-3 p-4">
          <div className="flex items-start gap-2">
            <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-status-fail" />
            <div className="min-w-0">
              <p className="text-sm font-medium text-foreground">
                Synthesis failed{run.currentStage ? ` at ${run.currentStage}` : ""}
              </p>
              {run.checkNotes ? (
                <p className="mt-1 break-words text-xs text-muted-foreground">{run.checkNotes}</p>
              ) : (
                <p className="mt-1 text-xs text-muted-foreground">
                  No stage detail was recorded for this run.
                </p>
              )}
            </div>
          </div>
          {logLines ? (
            <div>
              <p className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">
                Last log lines
              </p>
              <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded bg-surface-2 p-2 font-mono text-[11px] text-muted-foreground">
                {logLines.join("\n")}
              </pre>
            </div>
          ) : null}
        </div>
      </div>
    );
  }

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
