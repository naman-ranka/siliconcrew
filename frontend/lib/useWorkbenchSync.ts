import { useEffect, useRef } from "react";
import { useStore } from "@/lib/store";

// Terminal run states (both RunSummary "passed|failed" and SynthesisRun
// "completed|failed|…"). Anything else — running, queued, pending — is active.
const TERMINAL = new Set([
  "passed",
  "failed",
  "completed",
  "error",
  "cancelled",
  "canceled",
  "done",
  "skipped",
]);

export function isTerminal(status: string | null | undefined): boolean {
  return TERMINAL.has((status ?? "").toLowerCase());
}

/** True if any sim/synth run is still in a non-terminal state → worth watching
 *  the activity log for (drives the slow activity cadence + UI affordances). */
export function hasActiveRun(
  runs: { status: string }[],
  synthesisRuns: { status: string }[]
): boolean {
  return runs.some((r) => !isTerminal(r.status)) || synthesisRuns.some((r) => !isTerminal(r.status));
}

// Slow activity cadence while a run is in flight (a cheap head fetch of the
// tool-event log — NOT run status, NOT the whole workbench).
const ACTIVITY_POLL_MS = 15_000;

/**
 * Keeps the workbench fresh under the viewer model (Wave 9): the UI never
 * calls run-status on its own — run status is read by ACTORS (the agent, MCP
 * clients, the user via the Refresh button). Two triggers here:
 *   1. Revalidate on window focus / tab becoming visible — the "flip back to
 *      the browser" moment (loadSessions + loadWorkbench).
 *   2. While any run is non-terminal AND the tab is visible, revalidate the
 *      ACTIVITY slice every ~15s. The UI watches the LOG: when a new event
 *      carrying a runId lands, the store's activity observer pulls the runs
 *      list, and its transition detector owns unread/toasts. (SSE push can
 *      later replace this cadence without changing the model.)
 * The old 5s whole-workbench poll is gone. Idle tabs with no active run do
 * nothing on a timer.
 */
export function useWorkbenchSync(): void {
  const loadWorkbench = useStore((s) => s.loadWorkbench);
  const loadSessions = useStore((s) => s.loadSessions);
  const inFlight = useRef(false);

  useEffect(() => {
    const sync = async () => {
      if (inFlight.current) return;
      if (typeof document !== "undefined" && document.visibilityState !== "visible") return;
      inFlight.current = true;
      try {
        // Refresh the session list too, so a session created by another client
        // (e.g. the user's AI app via MCP) shows up — then the current session's
        // workbench (files/runs/synth) if one is selected.
        await loadSessions();
        if (useStore.getState().currentSession) await loadWorkbench();
      } finally {
        inFlight.current = false;
      }
    };

    const onFocus = () => void sync();
    const onVisible = () => {
      if (document.visibilityState === "visible") void sync();
    };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisible);

    const activityTick = setInterval(() => {
      if (typeof document !== "undefined" && document.visibilityState !== "visible") return;
      const { runs, synthesisRuns, currentSession, loadActivity } = useStore.getState();
      if (!currentSession) return;
      if (hasActiveRun(runs, synthesisRuns)) void loadActivity();
    }, ACTIVITY_POLL_MS);

    return () => {
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisible);
      clearInterval(activityTick);
    };
  }, [loadWorkbench, loadSessions]);
}
