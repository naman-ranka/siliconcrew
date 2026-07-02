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
import { FileExplorer } from "@/components/workbench/FileExplorer";
import { BottomDock } from "@/components/workbench/BottomDock";
import type { ActivityEvent } from "@/types";

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
      ],
      synthTop: "decoder",
      simTop: "decoder_tb",
      clockPeriodNs: 10,
      platform: "sky130hd",
    },
    runs: [],
    runsLoading: false,
    lintResult: null,
    synthJob: null,
    // Seed the lazy tree so FileExplorer renders without fetching.
    dirCache: {
      "": {
        status: "ready",
        entries: [
          { name: "decoder.v", path: "decoder.v", kind: "file" },
          { name: "decoder_tb.v", path: "decoder_tb.v", kind: "file" },
        ],
        error: null,
      },
    },
    activity: { serverEvents: [], localEvents: [], status: "ready", nextBefore: null, error: null },
  });
});

describe("FileExplorer", () => {
  it("renders the workspace tree from the dirCache with manifest role badges", () => {
    // jsdom reports 0x0 boxes, which makes @tanstack/react-virtual render no
    // rows — give the scroll viewport a real size so the tree materializes.
    const hSpy = vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(600);
    const wSpy = vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(300);
    render(<FileExplorer />);
    expect(screen.getByText("Explorer")).toBeInTheDocument();
    expect(screen.getByText("decoder.v")).toBeInTheDocument();
    expect(screen.getByText("decoder_tb.v")).toBeInTheDocument();
    // Root files carry their manifest roles.
    expect(screen.getByText("RTL")).toBeInTheDocument();
    expect(screen.getByText("TB")).toBeInTheDocument();
    hSpy.mockRestore();
    wSpy.mockRestore();
  });
});

describe("BottomDock", () => {
  it("shows Activity/Runs tabs with counts and lists runs on the Runs tab", () => {
    const ev: ActivityEvent = {
      id: "ev1",
      ts: new Date().toISOString(),
      source: "user",
      tool: "linter_tool",
      args: {},
      status: "ok",
      resultSummary: "passed",
      durationMs: 120,
      runId: null,
      threadId: null,
    };
    useStore.setState({
      runs: [
        {
          id: "sim_0001",
          kind: "sim",
          status: "failed",
          createdAt: new Date().toISOString(),
          top: "decoder_tb",
          pinned: false,
          failure: { type: "test_failed", timeNs: 240 },
        },
      ] as any,
      activity: {
        serverEvents: [ev],
        localEvents: [],
        status: "ready",
        nextBefore: null,
        error: null,
      },
    });

    render(<BottomDock />);
    expect(screen.getByRole("button", { name: /Activity/ })).toBeInTheDocument();

    // Switch to the Runs tab — the sim run row shows up with its failure time.
    fireEvent.click(screen.getByRole("button", { name: /Runs/ }));
    expect(screen.getByText("sim_0001")).toBeInTheDocument();
    expect(screen.getByText(/failed @ 240ns/)).toBeInTheDocument();
  });
});
