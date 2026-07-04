import { describe, it, expect } from "vitest";
import { isTerminal, hasActiveRun } from "@/lib/useWorkbenchSync";

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
    // The UI didn't start this job, but its list shows it non-terminal → poll.
    expect(hasActiveRun([], [{ status: "running" }])).toBe(true);
  });
});
