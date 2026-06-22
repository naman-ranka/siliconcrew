"use client";

import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import { Eye, CornerUpRight } from "lucide-react";
import { latestOfKind } from "./runStatus";

/**
 * "Viewing X" banner — the calm, blue (info) reminder that the artifacts below
 * reflect a specific run, not necessarily the latest. Offers a one-click jump
 * back to the latest run of that kind.
 */
export function ViewingBanner() {
  const { runs, selectedRunId, selectRun } = useStore();
  const run = runs.find((r) => r.id === selectedRunId);
  if (!run) return null;

  const latest = latestOfKind(runs, run.kind);
  const isLatest = latest?.id === run.id;

  const meta = [
    isLatest ? `latest ${run.kind}` : run.kind,
    run.top,
    run.status === "failed" && run.kind === "sim" && run.failure?.timeNs != null
      ? `failed @ ${run.failure.timeNs}ns`
      : run.status,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div
      className={cn(
        "flex items-center gap-2 px-3 py-1.5 text-xs border-b border-info/20 bg-info/5"
      )}
      data-testid="viewing-banner"
    >
      <Eye className="h-3.5 w-3.5 text-info" />
      <span className="text-muted-foreground">Viewing</span>
      <span className="font-mono text-info bg-info/10 px-1.5 py-0.5 rounded">{run.id}</span>
      <span className="text-muted-foreground truncate">· {meta}</span>
      {run.kind === "sim" && run.status === "failed" && run.failure?.firstFailureLine && (
        <span className="text-status-fail font-mono truncate max-w-[40%]" title={run.failure.firstFailureLine}>
          {run.failure.firstFailureLine}
        </span>
      )}
      {!isLatest && latest && (
        <button
          type="button"
          className="ml-auto flex items-center gap-1 text-info hover:underline shrink-0"
          onClick={() => void selectRun(latest.id)}
        >
          jump to latest <CornerUpRight className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}
