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

/** True if any sim/synth run is still in a non-terminal state → worth polling. */
export function hasActiveRun(
  runs: { status: string }[],
  synthesisRuns: { status: string }[]
): boolean {
  return runs.some((r) => !isTerminal(r.status)) || synthesisRuns.some((r) => !isTerminal(r.status));
}

const POLL_MS = 5000;

/**
 * Keeps the workbench fresh when ANOTHER client (e.g. the user's AI app via the
 * MCP) mutates the shared backend state. Two triggers:
 *   1. Revalidate on window focus / tab becoming visible — the "flip back to the
 *      browser" moment.
 *   2. Poll every few seconds while any run is non-terminal AND the tab is
 *      visible.
 * Both call loadWorkbench (manifest + runs + workspace), so MCP-created sessions,
 * files and run status show up without a manual reload — and a synth started by
 * another client is watched to completion (not just the UI's own job). Idle tabs
 * with no active run don't poll, so it's cheap.
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

    const poll = setInterval(() => {
      const { runs, synthesisRuns } = useStore.getState();
      if (hasActiveRun(runs, synthesisRuns)) void sync();
    }, POLL_MS);

    return () => {
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisible);
      clearInterval(poll);
    };
  }, [loadWorkbench, loadSessions]);
}
