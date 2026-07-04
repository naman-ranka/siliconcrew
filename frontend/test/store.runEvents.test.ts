import { describe, it, expect, beforeEach, vi } from "vitest";

// Wave 9 (Item 5): the UI is a viewer of the event log. These tests cover the
// three store mechanisms that replaced the old pollJob loop:
//   1. the runs-slice TRANSITION DETECTOR (running/queued → terminal ⇒ unread,
//      toast, dir invalidation, synth-artifact refresh),
//   2. the ACTIVITY OBSERVER (a new run-scoped event ⇒ loadRuns),
//   3. applyRunStatus (a Refresh/status payload updates the row + synthJob).

vi.mock("@/lib/api", () => ({
  projectsApi: {},
  sessionsApi: {},
  chatApi: {},
  threadsApi: {},
  modelsApi: {},
  workspaceApi: {},
  workbenchApi: {
    listRuns: vi.fn(),
    getActivity: vi.fn(),
  },
}));

import { useStore } from "@/lib/store";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { workbenchApi } from "@/lib/api";
import type { ActivityEvent, RunSummary } from "@/types";

const SESSION = {
  id: "s1",
  name: "s1",
  model_name: "m",
  project_id: null,
  created_at: null,
  updated_at: null,
  total_tokens: 0,
  total_cost: 0,
};

const synthRun = (id: string, status: RunSummary["status"]): RunSummary => ({
  id,
  kind: "synth",
  status,
  createdAt: new Date().toISOString(),
  top: "alu",
  pinned: false,
});

const event = (id: string, runId: string | null): ActivityEvent => ({
  id,
  ts: new Date().toISOString(),
  source: "user",
  tool: "get_synthesis_status",
  args: {},
  status: "ok",
  resultSummary: "",
  durationMs: 10,
  runId,
  threadId: null,
});

beforeEach(() => {
  vi.clearAllMocks();
  useWorkbenchUiStore.setState({ perSession: {} });
  useStore.setState({
    currentSession: SESSION as never,
    runs: [],
    toasts: [],
    synthJob: null,
    dirCache: {},
    activity: { serverEvents: [], localEvents: [], status: "empty", nextBefore: null, error: null },
  });
});

// ---- 1. transition detector -----------------------------------------------------

describe("runs-slice transition detector", () => {
  it("running → terminal on loadRuns marks unread, toasts, invalidates dirs, refreshes synth artifacts", async () => {
    const refreshSynthArtifacts = vi.fn().mockResolvedValue(undefined);
    const invalidateDirs = vi.fn();
    useStore.setState({
      runs: [synthRun("synth_0001", "running")],
      refreshSynthArtifacts,
      invalidateDirs,
      synthJob: { runId: "synth_0001", status: "running", currentStage: "route" },
    } as never);
    vi.mocked(workbenchApi.listRuns).mockResolvedValue([synthRun("synth_0001", "passed")]);

    await useStore.getState().loadRuns();

    expect(useWorkbenchUiStore.getState().perSession["s1"]?.unreadRunIds).toContain("synth_0001");
    expect(useStore.getState().toasts.some((t) => t.title === "Synthesis completed")).toBe(true);
    expect(invalidateDirs).toHaveBeenCalledWith(["", "synth_runs"]);
    expect(refreshSynthArtifacts).toHaveBeenCalledWith("synth_0001");
    // The last-known live status is history once the run is terminal.
    expect(useStore.getState().synthJob).toBeNull();
  });

  it("failure carries check_notes from the last-known status into the toast", async () => {
    useStore.setState({
      runs: [synthRun("synth_0001", "running")],
      refreshSynthArtifacts: vi.fn(),
      invalidateDirs: vi.fn(),
      synthJob: {
        runId: "synth_0001",
        status: "running",
        checkNotes: "orchestrator lost (backend restarted)",
      },
    } as never);
    vi.mocked(workbenchApi.listRuns).mockResolvedValue([synthRun("synth_0001", "failed")]);

    await useStore.getState().loadRuns();

    const toast = useStore.getState().toasts.find((t) => t.title === "Synthesis failed");
    expect(toast).toBeTruthy();
    expect(toast!.detail).toContain("orchestrator lost");
  });

  it("no transition → no unread/toast (steady running, or a run first seen terminal)", async () => {
    const invalidateDirs = vi.fn();
    useStore.setState({ runs: [synthRun("synth_0001", "running")], invalidateDirs } as never);
    // Steady running + a brand-new already-terminal row.
    vi.mocked(workbenchApi.listRuns).mockResolvedValue([
      synthRun("synth_0001", "running"),
      synthRun("synth_0000", "passed"),
    ]);

    await useStore.getState().loadRuns();

    expect(useWorkbenchUiStore.getState().perSession["s1"]?.unreadRunIds ?? []).toEqual([]);
    expect(useStore.getState().toasts).toEqual([]);
    expect(invalidateDirs).not.toHaveBeenCalled();
  });
});

// ---- 2. activity observer --------------------------------------------------------

describe("activity observer (new run-scoped event → loadRuns)", () => {
  it("a NEW head event carrying a runId triggers loadRuns", async () => {
    const loadRuns = vi.fn().mockResolvedValue(undefined);
    useStore.setState({
      loadRuns,
      activity: {
        serverEvents: [event("ev-1", null)],
        localEvents: [],
        status: "ready",
        nextBefore: null,
        error: null,
      },
    } as never);
    vi.mocked(workbenchApi.getActivity).mockResolvedValue({
      ok: true,
      events: [event("ev-2", "synth_0001"), event("ev-1", null)],
      nextBefore: null,
    });

    await useStore.getState().loadActivity();

    expect(loadRuns).toHaveBeenCalledTimes(1);
  });

  it("new events WITHOUT a runId (and already-known events) do not trigger loadRuns", async () => {
    const loadRuns = vi.fn().mockResolvedValue(undefined);
    useStore.setState({
      loadRuns,
      activity: {
        serverEvents: [event("ev-1", "synth_0001")],
        localEvents: [],
        status: "ready",
        nextBefore: null,
        error: null,
      },
    } as never);
    vi.mocked(workbenchApi.getActivity).mockResolvedValue({
      ok: true,
      events: [event("ev-3", null), event("ev-1", "synth_0001")],
      nextBefore: null,
    });

    await useStore.getState().loadActivity();

    expect(loadRuns).not.toHaveBeenCalled();
  });

  it("the very first page load never triggers (initial hydration loads runs anyway)", async () => {
    const loadRuns = vi.fn().mockResolvedValue(undefined);
    useStore.setState({ loadRuns } as never); // activity slice still "empty"
    vi.mocked(workbenchApi.getActivity).mockResolvedValue({
      ok: true,
      events: [event("ev-1", "synth_0001")],
      nextBefore: null,
    });

    await useStore.getState().loadActivity();

    expect(loadRuns).not.toHaveBeenCalled();
  });
});

// ---- 3. applyRunStatus -------------------------------------------------------------

describe("applyRunStatus", () => {
  it("updates the matching row + the synthJob last-known slice (non-terminal)", () => {
    useStore.setState({ runs: [synthRun("synth_0001", "running")] });

    useStore.getState().applyRunStatus({
      run_id: "synth_0001",
      status: "running",
      current_stage: "place",
      stage_history: [{ stage: "synth", status: "completed", ended_at: "2026-07-04T10:00:00Z" }],
      dispatched_at: "2026-07-04T09:50:00Z",
      last_log_lines: ["Placement 42% done"],
      elapsed_sec: 600,
      backend: "local_docker",
    });

    expect(useStore.getState().runs[0].status).toBe("running");
    const job = useStore.getState().synthJob;
    expect(job).toMatchObject({
      runId: "synth_0001",
      status: "running",
      currentStage: "place",
      dispatchedAt: "2026-07-04T09:50:00Z",
      elapsedSec: 600,
    });
    expect(job?.stageHistory).toHaveLength(1);
    expect(job?.lastLogLines).toEqual(["Placement 42% done"]);
  });

  it("a completed payload flips the row to passed and runs the transition detector", () => {
    const refreshSynthArtifacts = vi.fn().mockResolvedValue(undefined);
    const invalidateDirs = vi.fn();
    useStore.setState({
      runs: [synthRun("synth_0001", "running")],
      refreshSynthArtifacts,
      invalidateDirs,
    } as never);

    useStore.getState().applyRunStatus({ run_id: "synth_0001", status: "completed" });

    expect(useStore.getState().runs[0].status).toBe("passed");
    expect(useWorkbenchUiStore.getState().perSession["s1"]?.unreadRunIds).toContain("synth_0001");
    expect(useStore.getState().toasts.some((t) => t.title === "Synthesis completed")).toBe(true);
    expect(refreshSynthArtifacts).toHaveBeenCalledWith("synth_0001");
    expect(invalidateDirs).toHaveBeenCalledWith(["", "synth_runs"]);
    expect(useStore.getState().synthJob).toBeNull(); // cleared on terminal
  });

  it("ignores unknown_run and payloads without a run_id", () => {
    useStore.setState({ runs: [synthRun("synth_0001", "running")] });
    useStore.getState().applyRunStatus({ error: "unknown_run" });
    useStore.getState().applyRunStatus({ status: "completed" });
    expect(useStore.getState().runs[0].status).toBe("running");
    expect(useStore.getState().synthJob).toBeNull();
  });
});
