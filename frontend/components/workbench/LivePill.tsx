"use client";

import { useEffect, useState } from "react";
import { Check, Loader2, X } from "lucide-react";
import { useStore, selectActivity } from "@/lib/store";
import { useSessionUi } from "@/lib/workbenchUiStore";
import { cn } from "@/lib/utils";
import { relativeTime } from "./runStatus";

/**
 * The ONE honest status indicator in the top chrome (replaces v1's stage
 * dots): the latest activity event, tinted by its real status. Clicking it
 * opens the bottom dock on the Activity tab so the pill is always a doorway
 * to the full story, never a dead end.
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
  const { setDockCollapsed, setDockTab } = useSessionUi(currentSession?.id);

  // Re-render on an interval so "3m ago" stays honest without any event churn.
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 30_000);
    return () => clearInterval(id);
  }, []);

  const latest = events[0];
  if (!latest) return null;

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
  );
}
