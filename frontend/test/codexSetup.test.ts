import { describe, it, expect, beforeEach, vi } from "vitest";

// TTFT 3C (plans/codex-ttft-remediation.md): the Codex setup watch. Pre-warm
// fires for a Codex thread, the chip state mirrors the backend honestly
// (starting → ready), native threads show nothing, polling only runs while
// starting, and a thread switch supersedes a stale watch.

const prewarmRuntime = vi.fn();
const runtimeStatus = vi.fn();

vi.mock("@/lib/api", () => ({
  projectsApi: { list: vi.fn().mockResolvedValue([]) },
  sessionsApi: { list: vi.fn().mockResolvedValue([]) },
  threadsApi: {
    list: vi.fn().mockResolvedValue([]),
    getHistory: vi.fn().mockResolvedValue([]),
    prewarmRuntime: (...a: unknown[]) => prewarmRuntime(...a),
    runtimeStatus: (...a: unknown[]) => runtimeStatus(...a),
  },
  modelsApi: { list: vi.fn().mockResolvedValue({ models: [], default: "x" }) },
  chatApi: {
    createConnection: vi.fn(),
    getHistory: vi.fn().mockResolvedValue([]),
    getThreadHistory: vi.fn().mockResolvedValue([]),
  },
  workspaceApi: {},
  workbenchApi: {},
  codexApi: { status: vi.fn().mockResolvedValue({ connected: false, runtime_enabled: true }) },
  templatesApi: {},
  keysApi: {},
}));

import { useStore } from "@/lib/store";

const flush = () => new Promise((r) => setTimeout(r, 0));

beforeEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
  useStore.setState({
    currentSession: { id: "s1", name: "s1" } as never,
    activeThreadId: "th1",
    agentRuntime: "codex",
    codexSetup: null,
  } as never);
});

describe("prewarmAgentRuntime", () => {
  it("shows 'ready' immediately when the worker is already warm (no fake setup)", async () => {
    prewarmRuntime.mockResolvedValue({ state: "ready" });
    await useStore.getState().prewarmAgentRuntime();
    expect(prewarmRuntime).toHaveBeenCalledWith("s1", "th1");
    expect(useStore.getState().codexSetup).toEqual({ threadId: "th1", state: "ready" });
    expect(runtimeStatus).not.toHaveBeenCalled(); // ready → no polling at all
  });

  it("shows 'starting' then flips to 'ready' from the status endpoint", async () => {
    prewarmRuntime.mockResolvedValue({ state: "starting" });
    runtimeStatus.mockResolvedValue({ state: "ready" });
    await useStore.getState().prewarmAgentRuntime();
    expect(useStore.getState().codexSetup).toEqual({ threadId: "th1", state: "starting" });
    await new Promise((r) => setTimeout(r, 1300)); // one poll tick
    await flush();
    expect(useStore.getState().codexSetup).toEqual({ threadId: "th1", state: "ready" });
  }, 10_000);

  it("shows nothing for a runtime without warm capability (honest absence)", async () => {
    prewarmRuntime.mockResolvedValue({ state: "unavailable" });
    await useStore.getState().prewarmAgentRuntime();
    expect(useStore.getState().codexSetup).toBeNull();
  });

  it("no-ops (and clears) on a native thread — never calls the endpoint", async () => {
    useStore.setState({ agentRuntime: "langchain", codexSetup: { threadId: "th1", state: "ready" } } as never);
    await useStore.getState().prewarmAgentRuntime();
    expect(prewarmRuntime).not.toHaveBeenCalled();
    expect(useStore.getState().codexSetup).toBeNull();
  });

  it("a thread switch supersedes a stale watch (SWR iron rule)", async () => {
    let resolveFirst: (v: { state: string }) => void = () => {};
    prewarmRuntime.mockImplementationOnce(
      () => new Promise((r) => { resolveFirst = r; })
    );
    const first = useStore.getState().prewarmAgentRuntime(); // th1, hangs
    useStore.setState({ activeThreadId: "th2" } as never);
    prewarmRuntime.mockResolvedValue({ state: "ready" });
    await useStore.getState().prewarmAgentRuntime(); // th2 wins
    resolveFirst({ state: "starting" }); // stale th1 answer arrives late
    await first;
    await flush();
    expect(useStore.getState().codexSetup).toEqual({ threadId: "th2", state: "ready" });
  });

  it("clears the chip if the prewarm call itself fails", async () => {
    useStore.setState({ codexSetup: { threadId: "th1", state: "starting" } } as never);
    prewarmRuntime.mockRejectedValue(new Error("network"));
    await useStore.getState().prewarmAgentRuntime();
    expect(useStore.getState().codexSetup).toBeNull();
  });
});
