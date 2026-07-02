import { describe, it, expect, beforeEach, vi } from "vitest";

// Mock the API layer so the store tests run with no backend (Tier 1, jsdom).
vi.mock("@/lib/api", () => {
  return {
    projectsApi: {},
    sessionsApi: {},
    chatApi: {},
    threadsApi: {},
    workspaceApi: {
      getDir: vi.fn(),
      getDirPaths: vi.fn(),
      getFileSmart: vi.fn(),
      getWaveform: vi.fn(),
      getReport: vi.fn(),
    },
    workbenchApi: {
      getActivity: vi.fn(),
    },
  };
});

import { useStore, selectActivity } from "@/lib/store";
import { workspaceApi, workbenchApi } from "@/lib/api";
import type { ActivityEvent, DirEntry, SmartFile } from "@/types";

const SESSION = {
  id: "s1",
  name: "s1",
  model_name: "claude-sonnet-4-6",
  project_id: null,
  created_at: null,
  updated_at: null,
  total_tokens: 0,
  total_cost: 0,
};

const dirEntry = (name: string, kind: "dir" | "file" = "file"): DirEntry => ({
  name,
  path: name,
  kind,
});

const smartFile = (filename: string): SmartFile => ({
  filename,
  content: `// ${filename}`,
  size: 12,
  binary: false,
  tooLarge: false,
});

const activityEvent = (id: string, over: Partial<ActivityEvent> = {}): ActivityEvent => ({
  id,
  ts: "2026-07-01T10:00:00Z",
  source: "agent",
  tool: "write_file",
  args: {},
  status: "ok",
  resultSummary: "",
  durationMs: null,
  runId: null,
  threadId: null,
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  useStore.setState({
    currentSession: SESSION as any,
    runs: [],
    dirCache: {},
    fileCache: {},
    artifactCache: {},
    activity: { serverEvents: [], localEvents: [], status: "empty", nextBefore: null, error: null },
  });
});

describe("dirCache: loadDir", () => {
  it("is single-flight: two concurrent calls share ONE fetch", async () => {
    let resolve!: (v: unknown) => void;
    (workspaceApi.getDir as any).mockReturnValue(new Promise((r) => (resolve = r)));

    const a = useStore.getState().loadDir("");
    const b = useStore.getState().loadDir("");
    // A never-loaded dir shows "loading" (nothing to keep visible yet).
    expect(useStore.getState().dirCache[""].status).toBe("loading");
    resolve({ ok: true, path: "", entries: [dirEntry("counter.v")] });
    await Promise.all([a, b]);

    expect(workspaceApi.getDir).toHaveBeenCalledTimes(1);
    const slice = useStore.getState().dirCache[""];
    expect(slice.status).toBe("ready");
    expect(slice.entries.map((e) => e.name)).toEqual(["counter.v"]);
  });

  it("a ready dir is served from cache without a refetch", async () => {
    (workspaceApi.getDir as any).mockResolvedValue({ ok: true, path: "", entries: [dirEntry("a.v")] });
    await useStore.getState().loadDir("");
    await useStore.getState().loadDir("");
    expect(workspaceApi.getDir).toHaveBeenCalledTimes(1);
  });

  it("invalidateDirs refetches matching prefixes, keeping old entries visible (revalidating)", async () => {
    useStore.setState({
      dirCache: {
        "": { status: "ready", entries: [dirEntry("old-root.v")], error: null },
        sim_runs: { status: "ready", entries: [dirEntry("sim_0001", "dir")], error: null },
        "sim_runs/sim_0001": { status: "ready", entries: [dirEntry("dump.vcd")], error: null },
        src: { status: "ready", entries: [dirEntry("untouched.v")], error: null },
      },
    });
    let resolvers: Record<string, (v: unknown) => void> = {};
    (workspaceApi.getDir as any).mockImplementation(
      (_sid: string, path: string = "") => new Promise((r) => (resolvers[path] = r))
    );

    useStore.getState().invalidateDirs(["", "sim_runs"]);

    const s = useStore.getState();
    // SWR iron rule: populated slices revalidate — old entries stay visible.
    expect(s.dirCache[""].status).toBe("revalidating");
    expect(s.dirCache[""].entries.map((e) => e.name)).toEqual(["old-root.v"]);
    expect(s.dirCache["sim_runs"].status).toBe("revalidating");
    expect(s.dirCache["sim_runs/sim_0001"].status).toBe("revalidating");
    // Non-matching path untouched ("" matches root only, not every path).
    expect(s.dirCache["src"].status).toBe("ready");

    resolvers[""]({ ok: true, path: "", entries: [dirEntry("new-root.v")] });
    resolvers["sim_runs"]({ ok: true, path: "sim_runs", entries: [] });
    resolvers["sim_runs/sim_0001"]({ ok: true, path: "sim_runs/sim_0001", entries: [] });
    await new Promise((r) => setTimeout(r, 0));

    expect(useStore.getState().dirCache[""].status).toBe("ready");
    expect(useStore.getState().dirCache[""].entries.map((e) => e.name)).toEqual(["new-root.v"]);
  });

  it("a failed revalidate keeps the old entries and records the error", async () => {
    useStore.setState({
      dirCache: { "": { status: "ready", entries: [dirEntry("keep.v")], error: null } },
    });
    (workspaceApi.getDir as any).mockRejectedValue(new Error("boom"));

    await useStore.getState().loadDir("", { revalidate: true });

    const slice = useStore.getState().dirCache[""];
    expect(slice.status).toBe("error");
    expect(slice.entries.map((e) => e.name)).toEqual(["keep.v"]);
    expect(slice.error).toBe("boom");
  });
});

describe("fileCache: loadFile", () => {
  it("modified-match is a cache hit (no second fetch); mismatch refetches", async () => {
    (workspaceApi.getFileSmart as any).mockResolvedValue(smartFile("counter.v"));

    await useStore.getState().loadFile("counter.v", { modified: "m1" });
    expect(workspaceApi.getFileSmart).toHaveBeenCalledTimes(1);

    // Same modified stamp → cache hit.
    await useStore.getState().loadFile("counter.v", { modified: "m1" });
    expect(workspaceApi.getFileSmart).toHaveBeenCalledTimes(1);

    // New modified stamp → refetch.
    await useStore.getState().loadFile("counter.v", { modified: "m2" });
    expect(workspaceApi.getFileSmart).toHaveBeenCalledTimes(2);
    expect(useStore.getState().fileCache["counter.v"].modified).toBe("m2");
  });

  it("a null modified stamp is always stale (refetches every time)", async () => {
    (workspaceApi.getFileSmart as any).mockResolvedValue(smartFile("a.v"));
    await useStore.getState().loadFile("a.v");
    await useStore.getState().loadFile("a.v");
    expect(workspaceApi.getFileSmart).toHaveBeenCalledTimes(2);
  });

  it("a refetch keeps the old file visible (revalidating, never loading)", async () => {
    (workspaceApi.getFileSmart as any).mockResolvedValueOnce(smartFile("counter.v"));
    await useStore.getState().loadFile("counter.v", { modified: "m1" });

    let resolve!: (v: unknown) => void;
    (workspaceApi.getFileSmart as any).mockReturnValueOnce(new Promise((r) => (resolve = r)));
    const p = useStore.getState().loadFile("counter.v", { modified: "m2" });

    const during = useStore.getState().fileCache["counter.v"];
    expect(during.status).toBe("revalidating");
    expect(during.file?.content).toBe("// counter.v");

    resolve(smartFile("counter.v"));
    await p;
    expect(useStore.getState().fileCache["counter.v"].status).toBe("ready");
  });

  it("evicts least-recently-used entries beyond the cap of 30", async () => {
    (workspaceApi.getFileSmart as any).mockImplementation((_sid: string, path: string) =>
      Promise.resolve(smartFile(path))
    );

    for (let i = 0; i < 31; i++) {
      await useStore.getState().loadFile(`f${i}.v`, { modified: `m${i}` });
    }

    const cache = useStore.getState().fileCache;
    expect(Object.keys(cache)).toHaveLength(30);
    expect(cache["f0.v"]).toBeUndefined(); // oldest access evicted
    expect(cache["f30.v"]).toBeDefined();

    // Touching an old entry (cache hit) protects it from the next eviction.
    await useStore.getState().loadFile("f1.v", { modified: "m1" });
    await useStore.getState().loadFile("f31.v", { modified: "m31" });
    const after = useStore.getState().fileCache;
    expect(after["f1.v"]).toBeDefined();
    expect(after["f2.v"]).toBeUndefined();
  });
});

describe("artifactCache: loadArtifact", () => {
  it("terminal artifacts are cached forever (loader called once)", async () => {
    const loader = vi.fn().mockResolvedValue({ big: "waveform" });

    await useStore.getState().loadArtifact("wave:sim_0001", loader, { terminal: true });
    await useStore.getState().loadArtifact("wave:sim_0001", loader, { terminal: true });

    expect(loader).toHaveBeenCalledTimes(1);
    expect(useStore.getState().artifactCache["wave:sim_0001"].data).toEqual({ big: "waveform" });
  });

  it("non-terminal artifacts revalidate on each call, keeping data visible", async () => {
    const loader = vi.fn().mockResolvedValueOnce({ v: 1 });
    await useStore.getState().loadArtifact("report:synth_0001", loader, { terminal: false });
    expect(useStore.getState().artifactCache["report:synth_0001"].data).toEqual({ v: 1 });

    let resolve!: (v: unknown) => void;
    loader.mockReturnValueOnce(new Promise((r) => (resolve = r)));
    const p = useStore.getState().loadArtifact("report:synth_0001", loader, { terminal: false });

    const during = useStore.getState().artifactCache["report:synth_0001"];
    expect(during.status).toBe("revalidating"); // never back to "loading"
    expect(during.data).toEqual({ v: 1 }); // old data stays visible

    resolve({ v: 2 });
    await p;
    expect(loader).toHaveBeenCalledTimes(2);
    expect(useStore.getState().artifactCache["report:synth_0001"].data).toEqual({ v: 2 });
  });

  it("loadWaveformArtifact fetches the run's VCD and derives terminal from run status", async () => {
    useStore.setState({
      runs: [{ id: "sim_0001", kind: "sim", status: "passed", createdAt: null, top: "tb", pinned: false }] as any,
    });
    (workspaceApi.getWaveform as any).mockResolvedValue({ filename: "dump.vcd", endtime: 10, signals: [] });

    await useStore.getState().loadWaveformArtifact("sim_0001", "sim_runs/sim_0001/dump.vcd");
    await useStore.getState().loadWaveformArtifact("sim_0001", "sim_runs/sim_0001/dump.vcd");

    // Terminal (passed) → one fetch, cached forever.
    expect(workspaceApi.getWaveform).toHaveBeenCalledTimes(1);
    expect(workspaceApi.getWaveform).toHaveBeenCalledWith("s1", "sim_runs/sim_0001/dump.vcd");
    expect(useStore.getState().artifactCache["wave:sim_0001"].terminal).toBe(true);
  });

  it("loadReportArtifact treats a running run as non-terminal (revalidates)", async () => {
    useStore.setState({
      runs: [{ id: "synth_0001", kind: "synth", status: "running", createdAt: null, top: "t", pinned: false }] as any,
    });
    (workspaceApi.getReport as any).mockResolvedValue({ filename: "r.md", content: "# r", run_id: "synth_0001" });

    await useStore.getState().loadReportArtifact("synth_0001");
    await useStore.getState().loadReportArtifact("synth_0001");

    expect(workspaceApi.getReport).toHaveBeenCalledTimes(2);
    expect(workspaceApi.getReport).toHaveBeenCalledWith("s1", "synth_0001");
    expect(useStore.getState().artifactCache["report:synth_0001"].terminal).toBe(false);
  });
});

describe("activity: SWR iron rule + live merge", () => {
  it("a populated activity slice refetch never sets status 'loading'", async () => {
    useStore.setState({
      activity: {
        serverEvents: [activityEvent("srv-1")],
        localEvents: [],
        status: "ready",
        nextBefore: null,
        error: null,
      },
    });
    let resolve!: (v: unknown) => void;
    (workbenchApi.getActivity as any).mockReturnValue(new Promise((r) => (resolve = r)));

    const p = useStore.getState().loadActivity();
    expect(useStore.getState().activity.status).toBe("revalidating");
    expect(useStore.getState().activity.serverEvents).toHaveLength(1); // still visible

    resolve({ ok: true, events: [activityEvent("srv-2", { ts: "2026-07-01T11:00:00Z" }), activityEvent("srv-1")], nextBefore: null });
    await p;

    const a = useStore.getState().activity;
    expect(a.status).toBe("ready");
    expect(a.serverEvents.map((e) => e.id)).toEqual(["srv-2", "srv-1"]);
  });

  it("an empty slice loads with status 'loading' and lands ready", async () => {
    (workbenchApi.getActivity as any).mockResolvedValue({
      ok: true,
      events: [activityEvent("srv-1")],
      nextBefore: "srv-1",
    });

    const p = useStore.getState().loadActivity();
    expect(useStore.getState().activity.status).toBe("loading");
    await p;

    const a = useStore.getState().activity;
    expect(a.status).toBe("ready");
    expect(a.nextBefore).toBe("srv-1");
  });

  it("loadActivity({more}) appends the older page after nextBefore", async () => {
    useStore.setState({
      activity: {
        serverEvents: [activityEvent("srv-2", { ts: "2026-07-01T11:00:00Z" })],
        localEvents: [],
        status: "ready",
        nextBefore: "srv-2",
        error: null,
      },
    });
    (workbenchApi.getActivity as any).mockResolvedValue({
      ok: true,
      events: [activityEvent("srv-1")],
      nextBefore: null,
    });

    await useStore.getState().loadActivity({ more: true });

    expect(workbenchApi.getActivity).toHaveBeenCalledWith("s1", { limit: 50, before: "srv-2" });
    const a = useStore.getState().activity;
    expect(a.serverEvents.map((e) => e.id)).toEqual(["srv-2", "srv-1"]);
    expect(a.nextBefore).toBeNull();
  });

  it("selectActivity merges local WS events with server pages, newest-first, memoized", () => {
    const server = [activityEvent("srv-1", { ts: "2026-07-01T10:00:00Z" })];
    useStore.getState().appendLocalActivity(
      activityEvent("ws:tc9", { tool: "start_synthesis", status: "running", ts: "2026-07-01T12:00:00Z" })
    );
    useStore.setState({ activity: { ...useStore.getState().activity, serverEvents: server } });

    const merged = selectActivity(useStore.getState());
    expect(merged.map((e) => e.id)).toEqual(["ws:tc9", "srv-1"]);
    // Memoized: same inputs → same reference (safe as a zustand selector).
    expect(selectActivity(useStore.getState())).toBe(merged);
  });
});
