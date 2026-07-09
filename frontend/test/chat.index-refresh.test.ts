import { describe, it, expect, beforeEach, vi } from "vitest";

// X2A-4: the agent-shell artifact Index renders manifest.files + runs. Those
// slices must refresh off the SAME WS tool frames the inline cards render from
// (debounced) and again at turn completion — never via a poller.

const fake: any = { readyState: 0, onopen: null, onmessage: null, onerror: null, onclose: null, send: vi.fn(), close: vi.fn() };

const getManifest = vi.fn().mockResolvedValue({
  sessionId: "s1",
  files: [{ name: "alu.v", role: "rtl", path: "alu.v" }],
  synthTop: "alu",
  simTop: "tb",
  clockPeriodNs: 10,
  platform: "sky130hd",
});
const listRuns = vi.fn().mockResolvedValue([]);

vi.mock("@/lib/api", () => ({
  projectsApi: { list: vi.fn().mockResolvedValue([]) },
  sessionsApi: { list: vi.fn().mockResolvedValue([]) },
  threadsApi: { list: vi.fn().mockResolvedValue([]), getHistory: vi.fn().mockResolvedValue([]) },
  modelsApi: { list: vi.fn().mockResolvedValue({ models: [], default: "x" }) },
  chatApi: {
    createConnection: vi.fn(() => fake),
    getHistory: vi.fn().mockResolvedValue([]),
    getThreadHistory: vi.fn().mockResolvedValue([]),
  },
  workspaceApi: {
    listFiles: vi.fn().mockResolvedValue([]),
    listWaveforms: vi.fn().mockResolvedValue([]),
    listLayouts: vi.fn().mockResolvedValue({ layouts: [], missing_binaries: [] }),
    listSchematics: vi.fn().mockResolvedValue([]),
    listSynthesisRuns: vi.fn().mockResolvedValue([]),
  },
  workbenchApi: { getManifest: (...a: unknown[]) => getManifest(...a), listRuns: (...a: unknown[]) => listRuns(...a) },
  keysApi: {},
}));

import { useStore } from "@/lib/store";

const frame = (obj: unknown) => ({ data: JSON.stringify(obj) });

beforeEach(() => {
  vi.clearAllMocks();
  fake.onopen = fake.onmessage = fake.onerror = fake.onclose = null;
  fake.readyState = 0;
  useStore.setState({
    currentSession: { id: "s1", name: "s1" } as any,
    messages: [], activeThreadId: null,
    ws: null, wsSessionId: null, wsThreadId: null,
    isStreaming: false, streamingMessage: null, chatError: null, chatErrorCode: null,
  } as any);
});

// Drive a tool_call → tool_result pair through the live socket.
function toolFrame(sock: any, name: string, args: Record<string, unknown> = {}) {
  sock.onmessage(frame({ type: "tool_call", tool: { id: "t1", name, args } }));
  sock.onmessage(frame({ type: "tool_result", tool_call_id: "t1", status: "ok", content: "ok" }));
}

describe("X2A-4 — Index slices refresh off the activity flow", () => {
  it("a write_file frame schedules a debounced manifest reload (files accrue live)", () => {
    vi.useFakeTimers();
    try {
      useStore.getState().sendMessage("build a mux");
      const sock = useStore.getState().ws as any;
      toolFrame(sock, "write_file", { filename: "alu.v" });
      expect(getManifest).not.toHaveBeenCalled(); // debounced, not immediate
      vi.advanceTimersByTime(1300);
      expect(getManifest).toHaveBeenCalledTimes(1);
      expect(listRuns).not.toHaveBeenCalled(); // write_file doesn't touch runs
    } finally {
      vi.useRealTimers();
    }
  });

  it("a start_synthesis frame schedules a debounced runs reload", () => {
    vi.useFakeTimers();
    try {
      useStore.getState().sendMessage("synthesize");
      const sock = useStore.getState().ws as any;
      toolFrame(sock, "start_synthesis", {});
      vi.advanceTimersByTime(1300);
      expect(listRuns).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("turn completion (done) reconciles BOTH manifest and runs immediately", () => {
    useStore.getState().sendMessage("hi");
    const sock = useStore.getState().ws as any;
    sock.onmessage(frame({ type: "text", content: "done writing" }));
    sock.onmessage(frame({ type: "done", tokens: { input: 1, output: 1 } }));
    expect(getManifest).toHaveBeenCalled();
    expect(listRuns).toHaveBeenCalled();
  });

  it("a read-only frame (read_file) refreshes NEITHER slice", () => {
    vi.useFakeTimers();
    try {
      useStore.getState().sendMessage("read it");
      const sock = useStore.getState().ws as any;
      toolFrame(sock, "read_file", { filename: "alu.v" });
      vi.advanceTimersByTime(1300);
      expect(getManifest).not.toHaveBeenCalled();
      expect(listRuns).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });
});
