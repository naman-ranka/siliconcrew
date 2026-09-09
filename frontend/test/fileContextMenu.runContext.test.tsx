import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// dev#51 (2): right-click → Simulate on a file must carry the clicked file's
// context. Before this, run("sim") dropped `menu.path` entirely and the
// backend fell back to the manifest's default TB — the owner right-clicked
// sync_fifo_tb.v and watched a different testbench run.

vi.mock("@/lib/api", () => ({
  projectsApi: {},
  sessionsApi: {},
  chatApi: {},
  workspaceApi: { downloadRawFile: vi.fn() },
  // Mirrors the real detection: by CODE, never by message (W4/A17).
  isSignInRequired: (e: unknown) =>
    (e as { code?: string } | null)?.code === "signin_required",
  workbenchApi: {
    lint: vi.fn(),
    simulate: vi.fn(),
    synthesize: vi.fn(),
    retryRun: vi.fn(),
    listRuns: vi.fn().mockResolvedValue([]),
    getActivity: vi.fn().mockResolvedValue({ ok: true, events: [], nextBefore: null }),
  },
}));

import { useStore } from "@/lib/store";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { FileContextMenu } from "@/components/workbench/FileContextMenu";
import { workbenchApi } from "@/lib/api";
import type { DesignManifest, RunSummary } from "@/types";

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

const MANIFEST: DesignManifest = {
  sessionId: "s1",
  files: [
    { name: "sync_fifo.v", role: "rtl", path: "sync_fifo.v" },
    { name: "sync_fifo_tb.v", role: "tb", path: "sync_fifo_tb.v" },
  ],
  synthTop: "sync_fifo",
  simTop: "other_tb",
  clockPeriodNs: 10,
  platform: "sky130hd",
  testbenches: [{ file: "sync_fifo_tb.v", module: "sync_fifo_tb" }],
};

const SIM_RUN: RunSummary = {
  id: "sim_0001",
  kind: "sim",
  status: "passed",
  createdAt: null,
  top: "sync_fifo_tb",
  pinned: false,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(workbenchApi.listRuns).mockResolvedValue([]);
  vi.mocked(workbenchApi.getActivity).mockResolvedValue({
    ok: true,
    events: [],
    nextBefore: null,
  } as never);
  vi.mocked(workbenchApi.simulate).mockResolvedValue({ run: SIM_RUN, manifestWarnings: [] });
  useStore.setState({
    currentSession: SESSION as never,
    manifest: MANIFEST,
    runs: [],
    toasts: [],
    activity: { serverEvents: [], localEvents: [], status: "empty", nextBefore: null, error: null },
  });
  useWorkbenchUiStore.setState({ contextMenu: null });
});

describe("FileContextMenu run commands carry the clicked file", () => {
  it("Simulate on a testbench row sends THAT testbench as simTop", async () => {
    useWorkbenchUiStore.setState({
      contextMenu: { x: 10, y: 10, path: "sync_fifo_tb.v", kind: "file" },
    });
    render(<FileContextMenu />);

    fireEvent.click(screen.getByRole("menuitem", { name: /Simulate ⌘R/ }));

    await waitFor(() =>
      expect(workbenchApi.simulate).toHaveBeenCalledWith("s1", {
        mode: "rtl",
        simTop: "sync_fifo_tb", // the clicked file's module, NOT "other_tb"
      })
    );
  });

  it("Simulate on an rtl row keeps the manifest default (no false file scoping)", async () => {
    useWorkbenchUiStore.setState({
      contextMenu: { x: 10, y: 10, path: "sync_fifo.v", kind: "file" },
    });
    render(<FileContextMenu />);

    fireEvent.click(screen.getByRole("menuitem", { name: /Simulate ⌘R/ }));

    await waitFor(() =>
      expect(workbenchApi.simulate).toHaveBeenCalledWith("s1", {
        mode: "rtl",
        simTop: "other_tb",
      })
    );
  });
});
