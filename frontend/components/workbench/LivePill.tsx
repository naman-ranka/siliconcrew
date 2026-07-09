"use client";

import { useEffect, useState } from "react";
import { Check, Cpu, Loader2, X } from "lucide-react";
import { useStore, selectActivity } from "@/lib/store";
import { useSessionUi } from "@/lib/workbenchUiStore";
import { isTerminal } from "@/lib/useWorkbenchSync";
import { cn } from "@/lib/utils";
import { relativeTime } from "./runStatus";

/**
 * The honest status indicators in the top chrome (replaces v1's stage dots):
 *   1. The latest activity event, tinted by its real status. Clicking it
 *      opens the bottom dock on the Activity tab so the pill is always a
 *      doorway to the full story, never a dead end.
 *   2. When any run is non-terminal, a chip with its LAST-KNOWN state
 *      ("<run_id> · <stage or status> · last known") — explicitly labeled,
 *      no fake liveness: the UI never polls run status. Clicking it opens
 *      the dock on the Runs tab (where the Refresh gesture lives).
 */

// Friendly labels for the noisy tool names — everything else falls back to
// the raw tool name so nothing is ever mislabeled.
const TOOL_LABELS: Record<string, string> = {
  linter_tool: "Lint",
  run_isolated_simulation: "Sim",
  simulation_tool: "Sim",
  start_synthesis: "Synth",
  retry_pd: "P&R",
  write_file: "Write",
  edit_file_tool: "Write",
  write_spec: "Spec",
};

export function toolLabel(tool: string): string {
  return TOOL_LABELS[tool] ?? tool;
}

export function LivePill() {
  const events = useStore(selectActivity);
  const currentSession = useStore((s) => s.currentSession);
  const runs = useStore((s) => s.runs);
  const synthJob = useStore((s) => s.synthJob);
  const { setDockCollapsed, setDockTab } = useSessionUi(currentSession?.id);

  // Re-render on an interval so "3m ago" stays honest without any event churn.
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 30_000);
    return () => clearInterval(id);
  }, []);

  const latest = events[0];
  const activeRun = runs.find((r) => !isTerminal(r.status));
  if (!latest && !activeRun) return null;

  // Non-terminal run → last-known chip. Stage from the synthJob slice when it
  // matches (fed only by Refresh/status responses), else just the row status.
  const runChip = activeRun ? (
    <button
      type="button"
      data-testid="live-pill-run"
      title="Last-known state — the UI does not poll. Refresh from the Runs panel."
      onClick={() => {
        setDockCollapsed(false);
        setDockTab("runs");
      }}
      className={cn(
        "hidden md:flex h-6 shrink-0 items-center gap-1.5 rounded-full border px-2 text-[11px]",
        "border-status-running/40 text-status-running transition-colors hover:bg-surface-2",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
      )}
    >
      <Cpu className="h-3 w-3" aria-hidden />
      <span className="max-w-[220px] truncate font-mono">
        {activeRun.id} ·{" "}
        {synthJob?.runId === activeRun.id && synthJob.currentStage
          ? synthJob.currentStage
          : activeRun.status}{" "}
        · last known
      </span>
    </button>
  ) : null;

  if (!latest) return runChip;

  const tone =
    latest.status === "running"
      ? "border-status-running/40 text-status-running"
      : latest.status === "error"
      ? "border-status-fail/40 text-status-fail"
      : "border-status-pass/40 text-status-pass";

  const Icon =
    latest.status === "running" ? (
      <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
    ) : latest.status === "error" ? (
      <X className="h-3 w-3" aria-hidden />
    ) : (
      <Check className="h-3 w-3" aria-hidden />
    );

  const text = [
    `${toolLabel(latest.tool)} ${latest.runId ?? ""}`.trim(),
    latest.status === "ok" ? "done" : latest.status,
    relativeTime(latest.ts),
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <>
      {runChip}
      <button
        type="button"
        data-testid="live-pill"
        title={latest.resultSummary || undefined}
        onClick={() => {
          setDockCollapsed(false);
          setDockTab("activity");
        }}
        className={cn(
          "hidden md:flex h-6 shrink-0 items-center gap-1.5 rounded-full border px-2 text-[11px]",
          "transition-colors hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
          tone
        )}
      >
        {Icon}
        <span className="max-w-[280px] truncate">{text}</span>
      </button>
    </>
  );
}
