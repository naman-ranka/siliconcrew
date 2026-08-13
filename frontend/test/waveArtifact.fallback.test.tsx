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

// dev#51 (3): the no-VCD hint must diagnose the actual cause — a run whose
// compile failed never ran iverilog, so "add $dumpvars" was a misdiagnosis.
describe("WaveArtifact no-VCD hint branches on the run's failure", () => {
  const baseRun = {
    kind: "sim",
    createdAt: null,
    top: "sync_fifo_tb",
    pinned: false,
    vcdPath: "",
  };

  it("compile_failed → names the compile failure, never suggests $dumpvars", () => {
    useStore.setState({
      runs: [
        {
          ...baseRun,
          id: "sim_0100",
          status: "failed",
          failure: { type: "compile_failed", firstFailureLine: null, timeNs: null },
        },
      ] as any,
    });
    render(<WaveArtifact runId="sim_0100" />);
    expect(screen.getByText(/Compilation failed — the simulation never ran/)).toBeInTheDocument();
    expect(screen.queryByText(/\$dumpvars/)).toBeNull();
  });

  it("sim crash → names the failure type and first failure line", () => {
    useStore.setState({
      runs: [
        {
          ...baseRun,
          id: "sim_0101",
          status: "failed",
          failure: { type: "sim_failed", firstFailureLine: "vvp: fatal at 120ns", timeNs: 120 },
        },
      ] as any,
    });
    render(<WaveArtifact runId="sim_0101" />);
    expect(
      screen.getByText(/failed before producing a waveform \(sim_failed\) — vvp: fatal at 120ns/)
    ).toBeInTheDocument();
    expect(screen.queryByText(/\$dumpvars/)).toBeNull();
  });

  it("a completed run with no dump keeps the genuine $dumpvars hint", () => {
    useStore.setState({
      runs: [{ ...baseRun, id: "sim_0102", status: "passed", failure: null }] as any,
    });
    render(<WaveArtifact runId="sim_0102" />);
    expect(screen.getByText(/add \$dumpvars to the testbench/)).toBeInTheDocument();
  });

  it("test_failed also gets the $dumpvars hint — the sim DID run to its assertion", () => {
    useStore.setState({
      runs: [
        {
          ...baseRun,
          id: "sim_0103",
          status: "failed",
          failure: { type: "test_failed", firstFailureLine: "FAIL: y=1", timeNs: 40 },
        },
      ] as any,
    });
    render(<WaveArtifact runId="sim_0103" />);
    expect(screen.getByText(/add \$dumpvars to the testbench/)).toBeInTheDocument();
  });
});
