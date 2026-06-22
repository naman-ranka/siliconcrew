import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  projectsApi: {},
  sessionsApi: {},
  chatApi: {},
  workspaceApi: {},
  workbenchApi: {},
}));

import { useStore } from "@/lib/store";
import { FileTree } from "@/components/workbench/FileTree";
import { PipelineStepper } from "@/components/workbench/PipelineStepper";

const SESSION = {
  id: "s1",
  name: "s1",
  model_name: "x",
  project_id: null,
  created_at: null,
  updated_at: null,
  total_tokens: 0,
  total_cost: 0,
};

beforeEach(() => {
  useStore.setState({
    currentSession: SESSION as any,
    manifest: {
      sessionId: "s1",
      files: [
        { name: "decoder.v", role: "rtl", path: "decoder.v" },
        { name: "decoder_tb.v", role: "tb", path: "decoder_tb.v" },
        { name: "constraints.sdc", role: "sdc", path: "constraints.sdc" },
      ],
      synthTop: "decoder",
      simTop: "decoder_tb",
      clockPeriodNs: 10,
      platform: "sky130hd",
    },
    runs: [],
    lintResult: null,
    report: null,
    actionPending: { lint: false, sim: false, synth: false },
    activeArtifactTab: "spec",
  });
});

describe("FileTree", () => {
  it("renders manifest files with their role badges + tops", () => {
    render(<FileTree />);
    expect(screen.getByText("decoder.v")).toBeInTheDocument();
    expect(screen.getByText("decoder_tb.v")).toBeInTheDocument();
    expect(screen.getByText("RTL")).toBeInTheDocument();
    expect(screen.getByText("TB")).toBeInTheDocument();
    expect(screen.getByText("SDC")).toBeInTheDocument();
    expect(screen.getByText(/synthTop: decoder/)).toBeInTheDocument();
    expect(screen.getByText(/simTop: decoder_tb/)).toBeInTheDocument();
  });
});

describe("PipelineStepper", () => {
  it("surfaces the spine stages and the failing sim status", () => {
    useStore.setState({
      runs: [
        {
          id: "sim_0001",
          kind: "sim",
          status: "failed",
          createdAt: null,
          top: "decoder_tb",
          pinned: false,
          failure: { type: "test_failed", timeNs: 240 },
        },
      ] as any,
    });
    render(<PipelineStepper />);
    expect(screen.getByText("Simulate")).toBeInTheDocument();
    expect(screen.getByText("Synthesize")).toBeInTheDocument();
    expect(screen.getByText("fail @ 240ns")).toBeInTheDocument();
  });

  it("the Lint stage triggers the runLint action", () => {
    const runLint = vi.fn();
    useStore.setState({ runLint: runLint as any });
    render(<PipelineStepper />);
    fireEvent.click(screen.getByTitle(/Run Lint/));
    expect(runLint).toHaveBeenCalled();
  });
});
