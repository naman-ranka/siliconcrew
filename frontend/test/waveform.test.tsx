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
import { WaveformViewer } from "@/components/artifacts/WaveformViewer";

const SESSION = { id: "s1", name: "s1", model_name: "x", project_id: null, created_at: null, updated_at: null, total_tokens: 0, total_cost: 0 };

beforeEach(() => {
  useStore.setState({
    currentSession: SESSION as any,
    waveformFiles: ["sim_runs/sim_0001/counter.vcd"],
    selectedWaveform: "sim_runs/sim_0001/counter.vcd",
    // ps timescale: endtime 112000 ticks, 1e-12 s/tick. count steps by 2 (bug).
    waveformData: {
      filename: "counter.vcd",
      endtime: 112000,
      timescale: "1ps",
      unitSeconds: 1e-12,
      signalCount: 2,
      signals: [
        { name: "clk", full_name: "counter_tb.clk", scope: "counter_tb", width: 1, isBus: false, times: [0, 5000, 10000], values: [0, 1, 0], valuesStr: ["0", "1", "0"], xFlags: [false, false, false] },
        {
          name: "count", full_name: "counter_tb.count", scope: "counter_tb", width: 8, isBus: true,
          times: [0, 15000, 112000], values: [0, 2, 20],
          valuesStr: ["00000000", "00000010", "00010100"], xFlags: [false, false, false],
        },
      ],
    } as any,
    runs: [
      { id: "sim_0001", kind: "sim", status: "failed", createdAt: null, top: "counter_tb", pinned: false, vcdPath: "sim_runs/sim_0001/counter.vcd", failure: { type: "test_failed", timeNs: 112 } },
    ] as any,
    selectedRunId: "sim_0001",
  });
});

describe("WaveformViewer", () => {
  it("renders the scope tree and signals", () => {
    render(<WaveformViewer />);
    expect(screen.getByText("counter_tb")).toBeInTheDocument();
    expect(screen.getByText("count")).toBeInTheDocument();
    expect(screen.getByText(/2 scopes|signals/)).toBeInTheDocument();
  });

  it("shows the failure cursor time and the value-at-cursor (the bug value)", () => {
    render(<WaveformViewer />);
    // failure cursor chip at 112ns
    expect(screen.getByText(/fail @ 112ns/)).toBeInTheDocument();
    // value-at-cursor for the count bus at t=112ns is 20 → 0x14 (ns→ps mapping
    // resolves the cursor to tick 112000, the last change)
    expect(screen.getByText("=0x14")).toBeInTheDocument();
  });
});
