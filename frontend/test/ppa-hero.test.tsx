import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PpaHero, selectPpaView } from "@/components/artifacts/PpaHero";
import type { RunSummary } from "@/types";

function synth(id: string, ppa: Partial<RunSummary["ppa"]> | null): RunSummary {
  return {
    id,
    kind: "synth",
    status: "passed",
    createdAt: new Date().toISOString(),
    top: "cpu_top",
    pinned: false,
    ppa: ppa as RunSummary["ppa"],
  };
}

describe("selectPpaView", () => {
  it("picks the target synth run and the next-older one to compare", () => {
    const runs = [synth("synth_0003", { wnsNs: 0.5 }), synth("synth_0002", { wnsNs: 0.2 }), synth("synth_0001", { wnsNs: -0.1 })];
    const v = selectPpaView(runs, "synth_0002");
    expect(v?.current.id).toBe("synth_0002");
    expect(v?.previous?.id).toBe("synth_0001");
  });

  it("defaults to the newest synth run when no id given", () => {
    const runs = [synth("synth_0002", { wnsNs: 0.2 }), synth("synth_0001", { wnsNs: -0.1 })];
    expect(selectPpaView(runs, null)?.current.id).toBe("synth_0002");
  });

  it("returns null when there are no synth runs", () => {
    expect(selectPpaView([], null)).toBeNull();
  });
});

describe("PpaHero", () => {
  it("shows Timing met in green when WNS >= 0", () => {
    render(<PpaHero runs={[synth("synth_0001", { wnsNs: 0.85, areaUm2: 142, cells: 48 })]} runId="synth_0001" />);
    expect(screen.getByText("Timing met")).toBeInTheDocument();
    expect(screen.getByText(/0\.85 ns/)).toBeInTheDocument();
  });

  it("shows Timing violated when WNS < 0", () => {
    render(<PpaHero runs={[synth("synth_0001", { wnsNs: -0.3 })]} runId="synth_0001" />);
    expect(screen.getByText("Timing violated")).toBeInTheDocument();
  });

  it("renders nothing when the run has no PPA", () => {
    const { container } = render(<PpaHero runs={[synth("synth_0001", null)]} runId="synth_0001" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a NEUTRAL (never green) state for a null/unknown WNS", () => {
    // ppa object exists (so the hero renders) but WNS is null — must NOT claim
    // "Timing met" (green) and must read as not-computed.
    render(<PpaHero runs={[synth("synth_0001", { wnsNs: null, areaUm2: 142 })]} runId="synth_0001" />);
    expect(screen.queryByText("Timing met")).not.toBeInTheDocument();
    expect(screen.queryByText("Timing violated")).not.toBeInTheDocument();
    // The status pill reads "Not computed" and there is no status-pass coloring.
    const pills = screen.getAllByText("Not computed");
    expect(pills.length).toBeGreaterThan(0);
    expect(document.querySelector(".text-status-pass")).toBeNull();
  });

  it("renders null metrics (cells/Fmax/power) as a neutral 'Not computed' state", () => {
    render(
      <PpaHero
        runs={[synth("synth_0001", { wnsNs: 0.5, areaUm2: 142, cells: null, fmaxMhz: null, powerMw: null })]}
        runId="synth_0001"
      />
    );
    // WNS is met → green is OK here; but the three null metrics each show neutral.
    expect(screen.getByText("Timing met")).toBeInTheDocument();
    expect(screen.getAllByText("Not computed").length).toBeGreaterThanOrEqual(3);
  });
});
