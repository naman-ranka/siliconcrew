"use client";

import { useEffect } from "react";
import { Loader2, XCircle } from "lucide-react";
import { useStore } from "@/lib/store";
import { ReportViewer } from "@/components/artifacts/ReportViewer";
import { PpaHero } from "@/components/artifacts/PpaHero";
import { relativeTime } from "@/components/workbench/runStatus";
import type { ReportData } from "@/types";
import { ViewerError, ViewerSkeleton, ViewerSpinner } from "./panels";

/**
 * The log tail as the backend hands it to us, with its honest provenance label:
 * `source` is the backend's own wording ("final" / "partial (updated 16s ago)")
 * computed at RESPONSE time, so we pair it with when WE received that response
 * ("as of 2m ago") instead of implying the age keeps ticking. Static text — it
 * re-renders on state changes, never on a timer (invariants 4 and 6).
 */
function LogTail({
  lines,
  source,
  fetchedAt,
}: {
  lines: string[];
  source?: string | null;
  fetchedAt?: string | null;
}) {
  const asOf = relativeTime(fetchedAt);
  const label = [source || null, asOf ? `as of ${asOf}` : null].filter(Boolean).join(" · ");
  return (
    <div>
      <p className="mb-1 flex flex-wrap items-baseline gap-x-2 text-[10px] uppercase tracking-wide text-muted-foreground">
        <span>Last log lines</span>
        {label ? <span className="normal-case opacity-80">{label}</span> : null}
      </p>
      <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded bg-surface-2 p-2 font-mono text-[11px] text-muted-foreground">
        {lines.join("\n")}
      </pre>
    </div>
  );
}

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

  // The tail exists client-side ONLY when the last-known status slice is THIS
  // run — the UI is a viewer (invariant 6), so we never fetch it here.
  const liveLogLines =
    synthJob?.runId === runId && synthJob.lastLogLines?.length ? synthJob.lastLogLines : null;

  if (running) {
    if (!liveLogLines) {
      // Single-slot status store: another run (or no refresh yet) owns the slot.
      // Say so plainly rather than showing a bare spinner forever.
      return (
        <ViewerSpinner
          title="Synthesizing…"
          detail={`${runId} is still running — the report appears when the flow finishes. Live logs appear after the next status refresh.`}
        />
      );
    }
    return (
      <div className="flex h-full min-h-0 flex-col overflow-y-auto">
        <div className="flex flex-col items-center p-6 text-center">
          <Loader2 className="mb-3 h-6 w-6 animate-spin text-muted-foreground" />
          <p className="text-sm font-medium text-foreground">Synthesizing…</p>
          <p className="mt-1 max-w-[360px] text-xs text-muted-foreground">
            {runId} is still running — the report appears when the flow finishes.
          </p>
        </div>
        <div className="px-4 pb-4">
          <LogTail
            lines={liveLogLines}
            source={synthJob?.lastLogSource}
            fetchedAt={synthJob?.statusFetchedAt}
          />
        </div>
      </div>
    );
  }

  const data = (slice?.data ?? null) as ReportData | null;

  if (!data && run?.status === "failed") {
    // Honest failure panel (F12): a failed synth run rarely has a markdown
    // report, but it DOES carry the failing stage + a one-line reason, plus the
    // log tail when the last-known status slice is still this run.
    const hasPpa = run.kind === "synth" && run.ppa != null;
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
          {liveLogLines ? (
            <LogTail
              lines={liveLogLines}
              source={synthJob?.lastLogSource}
              fetchedAt={synthJob?.statusFetchedAt}
            />
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
