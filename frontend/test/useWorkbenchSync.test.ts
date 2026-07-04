import { describe, it, expect, afterEach, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { isTerminal, hasActiveRun, useWorkbenchSync } from "@/lib/useWorkbenchSync";
import { useStore } from "@/lib/store";

describe("run-activity predicates (drive polling)", () => {
  it("classifies terminal vs active statuses (case-insensitive)", () => {
    for (const t of ["passed", "failed", "completed", "COMPLETED", "cancelled", "done"]) {
      expect(isTerminal(t)).toBe(true);
    }
    for (const a of ["running", "queued", "pending", "", undefined as unknown as string]) {
      expect(isTerminal(a)).toBe(false);
    }
  });

  it("hasActiveRun is true if any run or synth run is non-terminal", () => {
    expect(hasActiveRun([{ status: "running" }], [])).toBe(true);
    expect(hasActiveRun([], [{ status: "queued" }])).toBe(true);
    expect(hasActiveRun([{ status: "passed" }], [{ status: "completed" }])).toBe(false);
    expect(hasActiveRun([], [])).toBe(false);
  });

  it("watches a synth started by another client (still 'running')", () => {
    // The UI didn't start this run, but its list shows it non-terminal →
    // worth watching the activity log for.
    expect(hasActiveRun([], [{ status: "running" }])).toBe(true);
  });
});

// Wave 9 interval semantics: the 5s whole-workbench poll is GONE. The only
// timer is a slow (~15s) revalidate of the ACTIVITY slice while a run is
// active — the UI watches the LOG, never run status / the whole workbench.
describe("useWorkbenchSync activity cadence (viewer model)", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  const RUNNING = {
    id: "synth_0001",
    kind: "synth",
    status: "running",
    createdAt: null,
    top: "alu",
    pinned: false,
  };

  it("revalidates ONLY the activity slice every ~15s while a run is active; stops when terminal", () => {
    vi.useFakeTimers();
    const loadActivity = vi.fn().mockResolvedValue(undefined);
    const loadWorkbench = vi.fn().mockResolvedValue(undefined);
    const loadSessions = vi.fn().mockResolvedValue(undefined);
    useStore.setState({
      currentSession: { id: "s1" },
      runs: [RUNNING],
      synthesisRuns: [],
      loadActivity,
      loadWorkbench,
      loadSessions,
    } as never);

    const { unmount } = renderHook(() => useWorkbenchSync());

    vi.advanceTimersByTime(15_000);
    expect(loadActivity).toHaveBeenCalledTimes(1);
    // The old 5s whole-workbench poll is gone: no timer-driven workbench or
    // session loads, ever.
    expect(loadWorkbench).not.toHaveBeenCalled();
    expect(loadSessions).not.toHaveBeenCalled();

    // Run reaches terminal → the cadence stops.
    useStore.setState({ runs: [{ ...RUNNING, status: "passed" }] } as never);
    vi.advanceTimersByTime(45_000);
    expect(loadActivity).toHaveBeenCalledTimes(1);

    unmount();
  });

  it("does nothing on a timer when no run is active", () => {
    vi.useFakeTimers();
    const loadActivity = vi.fn().mockResolvedValue(undefined);
    useStore.setState({
      currentSession: { id: "s1" },
      runs: [],
      synthesisRuns: [],
      loadActivity,
      loadWorkbench: vi.fn().mockResolvedValue(undefined),
      loadSessions: vi.fn().mockResolvedValue(undefined),
    } as never);

    const { unmount } = renderHook(() => useWorkbenchSync());
    vi.advanceTimersByTime(60_000);
    expect(loadActivity).not.toHaveBeenCalled();
    unmount();
  });
});
