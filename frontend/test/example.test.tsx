import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

/**
 * Tier-1 scaffold test — proves the Vitest + Testing Library (jsdom) harness
 * works with zero browser. Replace/extend with real workbench tests as Phase 1
 * builds it, e.g.:
 *   - file tree renders role badges from the manifest
 *   - "Run Sim" button calls the simulate endpoint and updates the run timeline
 *   - selecting a run flips the "viewing X" banner and the active artifact tab
 */
function RunButton({ stage }: { stage: string }) {
  return <button>Run {stage}</button>;
}

describe("verification harness (Tier 1, no browser)", () => {
  it("renders a component in jsdom", () => {
    render(<RunButton stage="Sim" />);
    expect(screen.getByRole("button")).toHaveTextContent("Run Sim");
  });
});
