"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Live elapsed-seconds clock, extracted from ToolCallCard's inline pattern
 * (command-surface-simplification W5/A21 — no shared timer utility existed).
 *
 * Counts from the moment `active` becomes true (or mount, when initially
 * true), ticking every 500ms; when `active` drops it FREEZES at its last
 * value (a finished 60s synth keeps reading 60s, not 0). A later re-activation
 * restarts from 0.
 *
 * This is a CLIENT-SIDE CLOCK, never a fetch — invariant 6 (the UI is a
 * viewer) stands: nothing here polls anything.
 */
export function useElapsedSeconds(active: boolean): number {
  const startedRef = useRef<number>(Date.now());
  const wasActiveRef = useRef(false);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!active) {
      // Freeze: keep the last value; remember we stopped so the next
      // activation restarts the clock.
      wasActiveRef.current = false;
      return;
    }
    if (!wasActiveRef.current) {
      wasActiveRef.current = true;
      startedRef.current = Date.now();
      setElapsed(0);
    }
    const id = setInterval(
      () => setElapsed(Math.round((Date.now() - startedRef.current) / 1000)),
      500
    );
    return () => clearInterval(id);
  }, [active]);

  return elapsed;
}
