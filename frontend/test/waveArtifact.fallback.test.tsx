import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  projectsApi: {},
  sessionsApi: {},
  chatApi: {},
  workspaceApi: { listWaveforms: vi.fn().mockResolvedValue([]), getWaveform: vi.fn() },
  workbenchApi: {},
}));

import { useStore } from "@/lib/store";
import { WaveArtifact } from "@/components/workbench/viewers/WaveArtifact";

const SESSION = { id: "s1", name: "s1", model_name: "x", project_id: null, created_at: null, updated_at: null, total_tokens: 0, total_cost: 0 };

const WAVE_DATA = {
  filename: "counter.vcd",
  endtime: 112000,
  timescale: "1ps",
  unitSeconds: 1e-12,
  signalCount: 1,
  signals: [
    { name: "clk", full_name: "counter_tb.clk", scope: "counter_tb", width: 1, isBus: false, times: [0, 5000, 10000], values: [0, 1, 0], valuesStr: ["0", "1", "0"], xFlags: [false, false, false] },
  ],
};

beforeEach(() => {
  useStore.setState({
    currentSession: SESSION as any,
    runs: [] as any, // the run is gone (GC'd / capped off the list)
    selectedRunId: null,
    artifactCache: {},
  } as any);
});

describe("WaveArtifact fallback for a cleaned-up run (#7)", () => {
  it("keeps showing a cached waveform when its run has dropped from the list", () => {
    // We loaded this run's VCD earlier this session; the slice is still cached
    // even though the run is no longer in `runs`.
    useStore.setState({
      artifactCache: {
        "wave:sim_0009": { status: "ready", data: WAVE_DATA, terminal: true, error: null, lastAccess: 1 },
      },
    } as any);

    render(<WaveArtifact runId="sim_0009" />);

    // The real cached waveform renders (a signal from it is visible)...
    expect(screen.getByText("counter_tb")).toBeInTheDocument();
    // ...with an honest note that the run is no longer listed...
    expect(screen.getByText(/no longer listed — cached waveform/)).toBeInTheDocument();
    // ...and NOT the dead-end "isn't in the run list" empty state.
    expect(screen.queryByText(/isn't in the run list/)).toBeNull();
  });

  it("still shows the honest empty state when the run is gone AND nothing is cached", () => {
    render(<WaveArtifact runId="sim_9999" />);
    expect(screen.getByText(/isn't in the run list/)).toBeInTheDocument();
  });
});
