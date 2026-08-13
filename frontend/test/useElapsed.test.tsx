import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";

import { useElapsedSeconds } from "@/lib/useElapsed";

// W5/A21: the shared elapsed clock extracted from ToolCallCard's inline
// pattern. Pure client-side timekeeping — the tests fake timers; nothing
// here ever fetches (invariant 6).
describe("useElapsedSeconds", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("ticks while active, freezes at its last value on stop, restarts on re-activation", () => {
    const { result, rerender } = renderHook(({ a }) => useElapsedSeconds(a), {
      initialProps: { a: true },
    });
    expect(result.current).toBe(0);
    act(() => vi.advanceTimersByTime(3000));
    expect(result.current).toBe(3);
    // Freeze: a finished 60s synth keeps reading its duration, not 0.
    rerender({ a: false });
    act(() => vi.advanceTimersByTime(5000));
    expect(result.current).toBe(3);
    // Re-activation restarts from 0.
    rerender({ a: true });
    expect(result.current).toBe(0);
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current).toBe(1);
  });

  it("an inactive mount shows 0 and never ticks (no bogus duration on reopened cards)", () => {
    const { result } = renderHook(() => useElapsedSeconds(false));
    act(() => vi.advanceTimersByTime(10_000));
    expect(result.current).toBe(0);
  });
});
